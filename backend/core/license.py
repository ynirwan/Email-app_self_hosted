"""
backend/core/license.py

Runtime license enforcement for ZeniPost Email Marketing Platform.

Supports two license file formats:

  v2  (zenipost-license-v2)  — issued by the ZeniPost Dashboard.
        Signature is a JWT (HS256) signed over the license payload.
        Verified with LICENSE_SIGNING_SECRET env var.
        Features are a string array: ["ab_testing", "automation", ...]
        Plan names: "starter" | "pro" | "agency"

  legacy  — old hand-issued format.
        Signature is an HMAC-SHA256 hex digest of canonical JSON.
        Features are a dict: {"ab_testing": true, "max_subscribers": -1, ...}
        Plan names: "starter" | "professional" | "enterprise"

In development mode (ENVIRONMENT=development) the signature check is bypassed
so dev environments work without a real license file.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plan name normalisation
# Dashboard uses "pro" / "agency"; internally we keep the old names for compat.
# ---------------------------------------------------------------------------

_PLAN_ALIASES: Dict[str, str] = {
    "starter":      "starter",
    "pro":          "professional",
    "professional": "professional",
    "agency":       "enterprise",
    "enterprise":   "enterprise",
}


def _normalize_plan(plan: str) -> str:
    return _PLAN_ALIASES.get(plan.strip().lower(), "starter")


# ---------------------------------------------------------------------------
# Plan definitions — canonical feature sets per tier.
# Used as the safe baseline; license overrides are merged on top.
# Deny-by-default: a missing key is always False / 0.
# ---------------------------------------------------------------------------

_PLAN_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "starter": {
        "ab_testing":              False,
        "automation":              False,
        "deliverability_dashboard": False,
        "segmentation":            False,   # Pro+ only
        "custom_smtp":             True,
        "api_access":              False,
        "audit_trail":             True,
        "max_domains":             0,       # uses license domain only; no custom domains
        "remote_db":               False,   # local Docker only
        "remote_redis":            False,   # local Docker only
        "multi_user":              False,
        "max_users":               1,
    },
    "professional": {
        "ab_testing":              True,
        "automation":              True,
        "deliverability_dashboard": True,
        "segmentation":            True,
        "custom_smtp":             True,
        "api_access":              True,
        "audit_trail":             True,
        "max_domains":             5,       # up to 5 domains, each with 1 tracking subdomain
        "remote_db":               True,
        "remote_redis":            True,
        "multi_user":              False,
        "max_users":               1,
    },
    "enterprise": {
        "ab_testing":              True,
        "automation":              True,
        "deliverability_dashboard": True,
        "segmentation":            True,
        "custom_smtp":             True,
        "api_access":              True,
        "audit_trail":             True,
        "max_domains":             -1,      # unlimited
        "remote_db":               True,
        "remote_redis":            True,
        "multi_user":              True,
        "max_users":               -1,      # unlimited
    },
}

# ---------------------------------------------------------------------------
# v2 feature-flag → internal feature key mapping
# Dashboard emits string flags; we translate them to the dict keys the app reads.
# ---------------------------------------------------------------------------

_V2_FLAG_MAP: Dict[str, str] = {
    "ab_testing":            "ab_testing",
    "automation":            "automation",
    "api_access":            "api_access",
    "audit_logs":            "audit_trail",       # name changed
    "segmentation_advanced": "segmentation",
    "analytics_advanced":    "deliverability_dashboard",
    "team_roles":            "multi_user",
    # Managed delivery flags — stored as booleans, no email-app equivalent yet
    "managed_delivery":      "managed_delivery",
    "dedicated_ip":          "dedicated_ip",
    "ip_warmup":             "ip_warmup",
    # These dashboard flags have no matching email-app gate; ignored gracefully
    # "campaign_management", "template_editors", "subscriber_management",
    # "analytics_basic", "suppression_list", "webhooks",
    # "gdpr_tools", "white_label", "client_usage"
}


def _features_from_v2(raw: dict) -> Dict[str, Any]:
    """
    Convert a v2 string-array features list into the email-app feature dict
    format expected by is_feature_enabled() and the rest of the app.

    No subscriber or email volume quotas are enforced — access is feature-gated
    only (ab_testing, automation, api_access, etc.).
    """
    plan_internal = _normalize_plan(raw.get("plan", "starter"))
    base = dict(_PLAN_DEFAULTS.get(plan_internal, _PLAN_DEFAULTS["starter"]))

    flag_list: List[str] = raw.get("features", [])

    # Boolean feature gates
    for flag in flag_list:
        internal_key = _V2_FLAG_MAP.get(flag)
        if internal_key:
            base[internal_key] = True

    return base


# ---------------------------------------------------------------------------
# Data class — what the rest of the app consumes
# ---------------------------------------------------------------------------

@dataclass
class LicenseInfo:
    valid:              bool = False
    plan:               str  = "starter"
    domain:             str  = ""
    root_domain:        str  = ""
    issued_to:          str  = ""
    issued_to_email:    str  = ""
    expires_at:         Optional[date] = None
    features:           Dict[str, Any] = field(default_factory=dict)
    error:              str  = ""

    # v2-only fields (None / False when loading legacy format)
    license_id:         Optional[str]  = None
    ping_url:           Optional[str]  = None
    admin_access_allowed: bool         = False
    delivery:           Optional[Dict[str, Any]] = None

    # ---------- convenience helpers -----------------------------------------

    def is_feature_enabled(self, feature: str) -> bool:
        """Return True if the current license includes *feature*."""
        val = self.features.get(feature)
        if isinstance(val, bool):
            return val
        if isinstance(val, int):
            return val != 0   # -1 = unlimited = enabled
        return bool(val)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return date.today() > self.expires_at

    def days_until_expiry(self) -> Optional[int]:
        if self.expires_at is None:
            return None
        return (self.expires_at - date.today()).days

    @property
    def allows_remote_db(self) -> bool:
        return bool(self.features.get("remote_db", False))

    @property
    def allows_remote_redis(self) -> bool:
        return bool(self.features.get("remote_redis", False))

    @property
    def has_managed_delivery(self) -> bool:
        return bool(self.features.get("managed_delivery", False))

    def to_public_dict(self) -> Dict[str, Any]:
        """Safe summary — never includes the raw signature or secret fields."""
        return {
            "license_id":           self.license_id,
            "plan":                 self.plan,
            "domain":               self.domain,
            "root_domain":          self.root_domain,
            "issued_to":            self.issued_to,
            "expires_at":           self.expires_at.isoformat() if self.expires_at else None,
            "days_until_expiry":    self.days_until_expiry(),
            "is_expired":           self.is_expired(),
            "admin_access_allowed": self.admin_access_allowed,
            "delivery":             self.delivery,
            "features":             self.features,
        }


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

_LICENSE_PATH_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent / "license.json",  # <repo_root>/license.json
    Path(__file__).resolve().parent.parent / "license.json",         # <backend>/license.json
    Path(os.getcwd()) / "license.json",
]


def _find_license_file() -> Optional[Path]:
    custom = os.getenv("LICENSE_FILE_PATH")
    if custom:
        p = Path(custom)
        if p.exists():
            return p
        logger.warning("LICENSE_FILE_PATH=%s not found, falling through", custom)
    for candidate in _LICENSE_PATH_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Signature verification — v2 (JWT) and legacy (HMAC-SHA256 hex)
# ---------------------------------------------------------------------------

def _license_secret() -> str:
    """Return the shared signing secret. Defaults match the dashboard default."""
    return os.getenv("LICENSE_SIGNING_SECRET", "zenipost-license-secret-2026")


def _verify_jwt_signature(raw: dict, signature: str) -> bool:
    """
    Verify a v2 JWT signature.
    The dashboard signs buildLicensePayload(lic, owner) with HS256.
    We decode the JWT and cross-check key tamper-sensitive fields.
    """
    from jose import JWTError
    from jose import jwt as jose_jwt

    secret = _license_secret()
    try:
        decoded = jose_jwt.decode(signature, secret, algorithms=["HS256"])
    except JWTError as exc:
        logger.warning("JWT license signature verification failed: %s", exc)
        return False

    # Tamper check: critical fields in the plain JSON must match the JWT payload.
    for check_key in ("license_id", "domain", "plan", "expires_at"):
        plain_val = raw.get(check_key)
        jwt_val   = decoded.get(check_key)
        if plain_val is not None and jwt_val is not None and plain_val != jwt_val:
            logger.warning(
                "License tamper detected: field '%s' differs between file (%r) and JWT (%r)",
                check_key, plain_val, jwt_val,
            )
            return False
    return True


def _verify_legacy_signature(raw: dict, signature: str) -> bool:
    """
    Verify the old HMAC-SHA256 hex-digest signature used by the legacy format.
    """
    secret_bytes = _license_secret().encode()
    payload = {k: v for k, v in raw.items() if k not in ("signature", "_comment")}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    expected = hmac.new(secret_bytes, canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.lower())


# ---------------------------------------------------------------------------
# Domain matching helper
# ---------------------------------------------------------------------------

def _domain_matches(app_domain: str, lic_domain: str, root_domain: str) -> bool:
    """
    Return True if *app_domain* is a valid installation target for a license
    issued for *lic_domain* / *root_domain*.

    Allowed cases:
      • Exact match          app.example.com == app.example.com
      • Root-domain match    app.example.com is a subdomain of example.com
        (covers installs on a subdomain of the licensed root domain)

    Bare IP addresses are allowed through — they are used in test installs
    and there is no meaningful domain to match against the license domain.
    """
    if not app_domain or not lic_domain:
        return True   # nothing to enforce; caller decides how strict to be

    # Bare IP — allow without domain matching
    import re as _re
    if _re.match(r"^\d{1,3}(\.\d{1,3}){3}$", app_domain):
        return True

    if app_domain == lic_domain:
        return True

    if root_domain:
        # app_domain is the root domain itself
        if app_domain == root_domain:
            return True
        # app_domain is a direct subdomain of root_domain
        if app_domain.endswith("." + root_domain):
            return True

    return False


# ---------------------------------------------------------------------------
# Date parsing — handles both "2027-01-01" and "2027-01-01T00:00:00.000Z"
# ---------------------------------------------------------------------------

def _parse_expires_at(raw_value: Any) -> Optional[date]:
    if not raw_value:
        return None
    s = str(raw_value)
    # ISO datetime with time component
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:26].rstrip("Z"), fmt.rstrip("Z")).date()
        except ValueError:
            pass
    # Plain date
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Legacy feature dict merge (unchanged from old loader)
# ---------------------------------------------------------------------------

def _merge_legacy_features(plan: str, override: dict) -> Dict[str, Any]:
    base = dict(_PLAN_DEFAULTS.get(plan, _PLAN_DEFAULTS["starter"]))
    for key, plan_val in base.items():
        if key in override:
            ov = override[key]
            if isinstance(plan_val, bool):
                base[key] = plan_val and bool(ov)
            elif isinstance(plan_val, int) and plan_val >= 0:
                if isinstance(ov, int):
                    base[key] = min(plan_val, ov) if ov >= 0 else plan_val
            else:
                base[key] = ov
    for key, ov in override.items():
        if key not in base:
            base[key] = ov
    return base


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

def load_license() -> LicenseInfo:
    """
    Load and validate license.json. Returns LicenseInfo(valid=False) on any
    problem; callers decide how hard to enforce. Never raises.
    """
    env    = os.getenv("ENVIRONMENT", "development").lower()
    is_dev = env == "development"

    license_path = _find_license_file()
    if license_path is None:
        msg = "license.json not found. Download it from the ZeniPost Dashboard."
        logger.warning(msg)
        if is_dev:
            logger.info("Development mode: using professional defaults without a license file.")
            return LicenseInfo(
                valid=True,
                plan="professional",
                features=dict(_PLAN_DEFAULTS["professional"]),
            )
        return LicenseInfo(valid=False, error=msg)

    try:
        raw = json.loads(license_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return LicenseInfo(valid=False, error=f"Could not parse license.json: {exc}")

    sig = raw.get("signature", "")

    # ── Detect format ──────────────────────────────────────────────────────
    is_v2 = raw.get("format") == "zenipost-license-v2"

    # ── Signature check ────────────────────────────────────────────────────
    placeholder = sig in ("", "REPLACE_WITH_ACTUAL_SIGNATURE_FROM_VENDOR")
    if not is_dev and placeholder:
        return LicenseInfo(valid=False, error="License has a placeholder signature. Download a real license from the Dashboard.")

    if not is_dev and not placeholder:
        if is_v2:
            ok = _verify_jwt_signature(raw, sig)
        else:
            ok = _verify_legacy_signature(raw, sig)
        if not ok:
            return LicenseInfo(valid=False, error="License signature invalid — file may have been tampered with.")

    # ── Parse plan & features ──────────────────────────────────────────────
    raw_plan      = raw.get("plan", "starter")
    plan_internal = _normalize_plan(raw_plan)

    if plan_internal not in _PLAN_DEFAULTS:
        return LicenseInfo(
            valid=False,
            error=f"Unknown plan '{raw_plan}'. Contact support.",
        )

    if is_v2:
        features = _features_from_v2(raw)
    else:
        features = _merge_legacy_features(plan_internal, raw.get("features", {}))

    # ── Parse dates ────────────────────────────────────────────────────────
    expires_at = _parse_expires_at(raw.get("expires_at", "9999-12-31"))

    # ── Field mapping — v2 uses different names ────────────────────────────
    if is_v2:
        issued_to       = raw.get("customer_name", raw.get("issued_to", ""))
        issued_to_email = raw.get("customer_email", raw.get("issued_to_email", ""))
    else:
        issued_to       = raw.get("issued_to", "")
        issued_to_email = raw.get("issued_to_email", "")

    # ── Build LicenseInfo ──────────────────────────────────────────────────
    info = LicenseInfo(
        valid=True,
        plan=plan_internal,
        domain=raw.get("domain", ""),
        root_domain=raw.get("root_domain", ""),
        issued_to=issued_to,
        issued_to_email=issued_to_email,
        expires_at=expires_at,
        features=features,
        # v2-only
        license_id=raw.get("license_id"),
        ping_url=raw.get("ping_url"),
        admin_access_allowed=bool(raw.get("admin_access_allowed", False)),
        delivery=raw.get("delivery"),
    )

    # ── Expiry check ───────────────────────────────────────────────────────
    if info.is_expired():
        info.valid = False
        info.error = f"License expired on {expires_at}. Please renew via the ZeniPost Dashboard."
        logger.error("License has expired: %s", expires_at)
        return info

    days = info.days_until_expiry()
    if days is not None and days <= 30:
        logger.warning("⚠️  License expires in %d day(s) on %s", days, expires_at)

    # ── Domain enforcement ────────────────────────────────────────────────
    # Verify that APP_DOMAIN env matches the domain this license was issued for.
    # This prevents a customer from re-using a license on a different domain.
    # Skipped in development (where APP_DOMAIN is often unset / "localhost").
    app_domain = os.getenv("APP_DOMAIN", "").strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
    if not is_dev and app_domain and info.domain:
        if not _domain_matches(app_domain, info.domain.lower(), info.root_domain.lower()):
            msg = (
                f"APP_DOMAIN='{app_domain}' does not match the licensed domain "
                f"'{info.domain}' (root: '{info.root_domain}'). "
                "Download a license issued for this domain from the ZeniPost Dashboard."
            )
            logger.error("❌ Domain mismatch: %s", msg)
            info.valid = False
            info.error = msg
            return info

    logger.info(
        "✅ License loaded — format=%s plan=%s issued_to=%s expires=%s domain=%s",
        "v2" if is_v2 else "legacy",
        plan_internal, issued_to, expires_at, info.domain,
    )
    return info


# ---------------------------------------------------------------------------
# Singleton — loaded once on first import
# ---------------------------------------------------------------------------

_license_cache: Optional[LicenseInfo] = None


def get_license() -> LicenseInfo:
    """Return the cached LicenseInfo, loading it on first call."""
    global _license_cache
    if _license_cache is None:
        _license_cache = load_license()
    return _license_cache


def reload_license() -> LicenseInfo:
    """Force a fresh load — call this after install.py writes a new license.json."""
    global _license_cache
    _license_cache = load_license()
    return _license_cache


def require_feature(feature: str) -> None:
    """
    Raise RuntimeError if the current license does not include *feature*.
    Call inside route handlers or service functions to gate plan-specific behaviour.

    Example:
        from core.license import require_feature
        require_feature("ab_testing")
    """
    lic = get_license()
    if not lic.valid:
        raise RuntimeError(f"License invalid: {lic.error}")
    if not lic.is_feature_enabled(feature):
        raise RuntimeError(
            f"Feature '{feature}' is not included in your '{lic.plan}' plan. "
            "Please upgrade your license via the ZeniPost Dashboard."
        )


# ---------------------------------------------------------------------------
# FastAPI dependency factory
# ---------------------------------------------------------------------------

def license_feature(feature: str):
    """
    FastAPI dependency factory — returns a dependency that raises HTTP 403
    when *feature* is not enabled on the current license.

    Usage in main.py (preferred — gates the whole router):
        from core.license import license_feature
        from fastapi import Depends

        app.include_router(
            ab_testing.router,
            prefix="/api",
            dependencies=[Depends(license_feature("ab_testing"))],
        )

    Usage inside a single route:
        @router.get("/some-endpoint")
        async def handler(_: None = Depends(license_feature("ab_testing"))):
            ...
    """
    from fastapi import HTTPException  # lazy import — avoids circular at module load

    async def _check() -> None:
        lic = get_license()
        if not lic.valid:
            raise HTTPException(
                status_code=403,
                detail=f"License invalid: {lic.error}",
            )
        if not lic.is_feature_enabled(feature):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"The '{feature}' feature is not available on your "
                    f"'{lic.plan}' plan. "
                    "Please upgrade your license via the ZeniPost Dashboard."
                ),
            )

    return _check
