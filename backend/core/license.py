"""
backend/core/license.py

Runtime license enforcement for ZeniPost Email Marketing Platform.

Reads license.json from the project root at startup. Exposes a LicenseInfo
object with the current plan's feature flags so routes and the setup wizard
can gate features without touching application logic directly.

Signature verification uses HMAC-SHA256 over a canonical JSON payload with
a vendor-supplied shared secret (LICENSE_SIGNING_SECRET env var).  In
development mode the signature check is bypassed so dev environments work
without a real license file.
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
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plan definitions — canonical feature sets per tier.
# A real license.json overrides individual features; this is the baseline
# so a missing key always has a safe default (deny rather than allow).
# ---------------------------------------------------------------------------

_PLAN_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "starter": {
        "ab_testing": False,
        "automation": False,
        "deliverability_dashboard": False,
        "segmentation": True,
        "custom_smtp": True,
        "api_access": False,
        "audit_trail": True,
        "remote_db": False,        # local Docker only
        "remote_redis": False,     # local Docker only
        "multi_user": False,
        "max_subscribers": 10_000,
        "max_campaigns_per_month": 10,
        "max_users": 1,
    },
    "professional": {
        "ab_testing": True,
        "automation": True,
        "deliverability_dashboard": True,
        "segmentation": True,
        "custom_smtp": True,
        "api_access": True,
        "audit_trail": True,
        "remote_db": True,
        "remote_redis": True,
        "multi_user": False,
        "max_subscribers": -1,      # unlimited
        "max_campaigns_per_month": -1,
        "max_users": 1,
    },
    "enterprise": {
        "ab_testing": True,
        "automation": True,
        "deliverability_dashboard": True,
        "segmentation": True,
        "custom_smtp": True,
        "api_access": True,
        "audit_trail": True,
        "remote_db": True,
        "remote_redis": True,
        "multi_user": True,
        "max_subscribers": -1,
        "max_campaigns_per_month": -1,
        "max_users": -1,           # unlimited
    },
}


# ---------------------------------------------------------------------------
# Data class — what the rest of the app consumes
# ---------------------------------------------------------------------------

@dataclass
class LicenseInfo:
    valid: bool = False
    plan: str = "starter"
    domain: str = ""
    issued_to: str = ""
    issued_to_email: str = ""
    expires_at: Optional[date] = None
    features: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    # ---------- convenience helpers -----------------------------------------

    def is_feature_enabled(self, feature: str) -> bool:
        """Return True if the current plan includes *feature*."""
        val = self.features.get(feature)
        if isinstance(val, bool):
            return val
        if isinstance(val, int):
            return val != 0  # -1 = unlimited = enabled
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
        return self.features.get("remote_db", False)

    @property
    def allows_remote_redis(self) -> bool:
        return self.features.get("remote_redis", False)

    def to_public_dict(self) -> Dict[str, Any]:
        """Safe summary — never includes the raw license key or signature."""
        return {
            "plan": self.plan,
            "domain": self.domain,
            "issued_to": self.issued_to,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "days_until_expiry": self.days_until_expiry(),
            "is_expired": self.is_expired(),
            "features": self.features,
        }


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

# Resolved once at module import and cached.  install.py also imports this
# module to do pre-flight validation, so keep the path discovery robust.
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


def _signing_secret() -> Optional[bytes]:
    secret = os.getenv("LICENSE_SIGNING_SECRET", "")
    if not secret:
        return None
    return secret.encode()


def _build_canonical_payload(data: dict) -> bytes:
    """
    Canonical JSON for HMAC: sort keys, no spaces.
    Fields excluded from the signature: 'signature' itself and '_comment'.
    """
    payload = {
        k: v for k, v in data.items()
        if k not in ("signature", "_comment")
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _verify_signature(data: dict, signature: str) -> bool:
    secret = _signing_secret()
    if secret is None:
        # No secret configured — skip verification (dev/trial mode).
        logger.debug("LICENSE_SIGNING_SECRET not set; skipping signature check")
        return True
    canonical = _build_canonical_payload(data)
    expected = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.lower())


def _merge_features(plan: str, override: dict) -> Dict[str, Any]:
    base = dict(_PLAN_DEFAULTS.get(plan, _PLAN_DEFAULTS["starter"]))
    # Only allow overrides to *lower* limits, never raise them above plan cap.
    # Boolean features: the plan baseline wins if override tries to add a
    # feature the plan doesn't include.
    for key, plan_val in base.items():
        if key in override:
            ov = override[key]
            if isinstance(plan_val, bool):
                # Override can disable a feature but can't enable one the plan
                # doesn't include.
                base[key] = plan_val and bool(ov)
            elif isinstance(plan_val, int) and plan_val >= 0:
                # -1 = unlimited; if plan is capped, use the smaller limit.
                if isinstance(ov, int):
                    base[key] = min(plan_val, ov) if ov >= 0 else plan_val
            else:
                base[key] = ov
    # Allow overrides to add keys not in the plan baseline (future features).
    for key, ov in override.items():
        if key not in base:
            base[key] = ov
    return base


def load_license() -> LicenseInfo:
    """
    Load and validate the license file.  Returns a LicenseInfo with
    valid=False if anything is wrong; callers decide how hard to enforce.
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    is_dev = env == "development"

    license_path = _find_license_file()
    if license_path is None:
        msg = "license.json not found. Run install.py to set up the application."
        logger.warning(msg)
        if is_dev:
            logger.info("Development mode: using starter defaults without a license file.")
            return LicenseInfo(
                valid=True,
                plan="starter",
                features=dict(_PLAN_DEFAULTS["starter"]),
                error="",
            )
        return LicenseInfo(valid=False, error=msg)

    try:
        raw = json.loads(license_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return LicenseInfo(valid=False, error=f"Could not parse license.json: {exc}")

    # Signature check
    sig = raw.get("signature", "")
    if not is_dev and sig in ("", "REPLACE_WITH_ACTUAL_SIGNATURE_FROM_VENDOR"):
        return LicenseInfo(valid=False, error="License has a placeholder signature. Use a real license.")

    if not is_dev and not _verify_signature(raw, sig):
        return LicenseInfo(valid=False, error="License signature invalid — file may have been tampered with.")

    # Parse dates
    try:
        expires_at = date.fromisoformat(raw.get("expires_at", "9999-12-31"))
    except ValueError:
        expires_at = None

    plan = raw.get("plan", "starter").lower()
    if plan not in _PLAN_DEFAULTS:
        return LicenseInfo(valid=False, error=f"Unknown plan '{plan}'. Valid plans: {list(_PLAN_DEFAULTS.keys())}")

    features = _merge_features(plan, raw.get("features", {}))

    info = LicenseInfo(
        valid=True,
        plan=plan,
        domain=raw.get("domain", ""),
        issued_to=raw.get("issued_to", ""),
        issued_to_email=raw.get("issued_to_email", ""),
        expires_at=expires_at,
        features=features,
        error="",
    )

    if info.is_expired():
        info.valid = False
        info.error = f"License expired on {expires_at}. Please renew."
        logger.error("License has expired: %s", expires_at)
        return info

    days = info.days_until_expiry()
    if days is not None and days <= 30:
        logger.warning("License expires in %d day(s) on %s", days, expires_at)

    logger.info(
        "License loaded — plan=%s issued_to=%s expires=%s",
        info.plan, info.issued_to, expires_at,
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
    """Force a fresh load (useful after install.py writes license.json)."""
    global _license_cache
    _license_cache = load_license()
    return _license_cache


def require_feature(feature: str) -> None:
    """
    Raise a RuntimeError if the current license does not include *feature*.
    Import and call this inside route handlers or service functions that
    should be gated by plan.
    """
    lic = get_license()
    if not lic.valid:
        raise RuntimeError(f"License invalid: {lic.error}")
    if not lic.is_feature_enabled(feature):
        raise RuntimeError(
            f"Feature '{feature}' is not included in your '{lic.plan}' plan. "
            "Please upgrade your license."
        )
