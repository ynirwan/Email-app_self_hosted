"""
backend/tasks/license_ping_task.py

Periodic Celery task that pings the ZeniPost Dashboard to confirm license
validity and receive any updated configuration (delivery plan changes, quota
adjustments, expiry warnings).

Runs once per day via Celery Beat.

Ping request:  POST <ping_url>   { "domain": "...", "signature": "..." }
Ping response: { valid, status, plan, emails_per_month, subscribers_limit,
                 features, expires_at, admin_access_allowed, delivery, message }

On success the local license cache is refreshed so the app picks up any
changes without requiring a restart.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


def _do_ping() -> dict:
    """
    Synchronous ping implementation — called inside the Celery task.
    Returns a result dict with keys: success, message, changes.
    """
    import httpx
    from core.license import get_license, reload_license

    lic = get_license()

    if not lic.valid:
        return {
            "success": False,
            "message": f"Skipping ping — license invalid: {lic.error}",
            "changes": [],
        }

    ping_url = lic.ping_url
    if not ping_url:
        return {
            "success": False,
            "message": "Skipping ping — no ping_url in license (legacy format or dev mode).",
            "changes": [],
        }

    domain    = lic.domain
    # The license signature field contains the JWT — that's what the dashboard expects
    import json
    from pathlib import Path

    # Re-read the raw license file to get the signature JWT
    from core.license import _find_license_file
    license_path = _find_license_file()
    if license_path is None:
        return {"success": False, "message": "license.json not found", "changes": []}

    try:
        raw = json.loads(license_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"success": False, "message": f"Could not read license.json: {exc}", "changes": []}

    signature = raw.get("signature", "")
    if not signature:
        return {"success": False, "message": "No signature in license file", "changes": []}

    # Best-effort: include the server's outbound IP so the dashboard can record
    # lastPingIp and detect if this installation has moved to a different server.
    server_ip: str = ""
    try:
        import socket as _socket
        with _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM) as _s:
            _s.connect(("8.8.8.8", 80))
            server_ip = _s.getsockname()[0]
    except Exception:
        pass

    # Send ping
    try:
        response = httpx.post(
            ping_url,
            json={"domain": domain, "signature": signature, "server_ip": server_ip},
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException:
        logger.warning("License ping timed out: %s", ping_url)
        return {"success": False, "message": "Ping timed out", "changes": []}
    except httpx.HTTPStatusError as exc:
        logger.warning("License ping returned %s: %s", exc.response.status_code, ping_url)
        return {"success": False, "message": f"Ping HTTP {exc.response.status_code}", "changes": []}
    except Exception as exc:
        logger.warning("License ping failed: %s", exc)
        return {"success": False, "message": str(exc), "changes": []}

    # ── Handle response ───────────────────────────────────────────────────
    changes: list[str] = []

    if not data.get("valid", False):
        ping_status = data.get("status", "unknown")
        msg         = data.get("message", "License invalid per Dashboard")
        logger.error("❌ License ping: INVALID — status=%s message=%s", ping_status, msg)

        if ping_status in ("revoked", "expired"):
            # Force a reload so the app immediately reflects the new state.
            reload_license()
            changes.append(f"License marked {ping_status} — reloaded")

        return {"success": False, "message": msg, "status": ping_status, "changes": changes}

    # Detect notable changes in the response vs. our cached state
    resp_plan = data.get("plan")
    if resp_plan and resp_plan != lic.plan:
        changes.append(f"Plan changed: {lic.plan} → {resp_plan}")

    resp_subs = data.get("subscribers_limit")
    if isinstance(resp_subs, int) and resp_subs != lic.features.get("max_subscribers"):
        changes.append(f"Subscriber limit updated: {resp_subs}")

    delivery_changed = bool(data.get("delivery")) != bool(lic.delivery)
    if delivery_changed:
        changes.append("Delivery plan changed")

    resp_admin = data.get("admin_access_allowed", False)
    if resp_admin != lic.admin_access_allowed:
        changes.append(f"admin_access_allowed: {lic.admin_access_allowed} → {resp_admin}")

    if changes:
        logger.info("License ping: changes detected — reloading: %s", changes)
        reload_license()

    # Warn if the dashboard detected a server IP mismatch (potential license reuse)
    if data.get("ip_mismatch"):
        logger.warning(
            "⚠️  License IP mismatch detected by dashboard — this license may be "
            "installed on multiple servers. Contact support@zenipost.com if this is unexpected."
        )

    ping_status = data.get("status", "active")
    msg         = data.get("message", "License valid.")

    if ping_status == "expiring":
        logger.warning("⚠️  License ping: %s", msg)
    else:
        logger.info("✅ License ping OK — status=%s plan=%s", ping_status, data.get("plan"))

    return {
        "success": True,
        "message": msg,
        "status":  ping_status,
        "changes": changes,
        "pinged_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

def register_ping_task(celery_app):
    """
    Register the license ping task on the given Celery app.
    Called from celery_app.py after the app is created.

    Usage in celery_app.py:
        from tasks.license_ping_task import register_ping_task
        register_ping_task(celery_app)
    """

    @celery_app.task(
        name="tasks.license_ping",
        bind=True,
        max_retries=2,
        default_retry_delay=300,   # 5 min retry on transient failures
        acks_late=True,
        ignore_result=True,
    )
    def license_ping(self):
        """Daily license validity ping to ZeniPost Dashboard."""
        try:
            result = _do_ping()
            if not result["success"] and result.get("status") not in ("revoked", "expired"):
                # Transient error — retry up to max_retries
                raise self.retry(exc=RuntimeError(result["message"]))
            return result
        except Exception as exc:
            logger.error("License ping task error: %s", exc, exc_info=True)
            raise

    return license_ping
