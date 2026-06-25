# config/security.py
from cryptography.fernet import Fernet
import base64
import hashlib
import hmac
import logging
import time
from typing import Optional, Dict, Tuple

from core.config import settings

logger = logging.getLogger(__name__)

class SecureConfigManager:
    def __init__(self):
        master_key = settings.MASTER_ENCRYPTION_KEY
        if not master_key:
            raise ValueError("MASTER_ENCRYPTION_KEY required")
        
        self.cipher = Fernet(master_key.encode())
    
    def encrypt_config(self, config: dict) -> dict:
        """Encrypt sensitive configuration values"""
        encrypted_config = config.copy()
        
        sensitive_fields = ['password', 'api_key', 'smtp_password', 'webhook_secret']
        
        for field in sensitive_fields:
            if field in config and config[field]:
                encrypted_config[field] = self.cipher.encrypt(
                    config[field].encode()
                ).decode()
                encrypted_config[f"{field}_encrypted"] = True
        
        return encrypted_config
    
    def decrypt_config(self, config: dict) -> dict:
        """Decrypt configuration for use"""
        decrypted_config = config.copy()
        
        for key, value in config.items():
            if key.endswith('_encrypted') and value:
                field_name = key.replace('_encrypted', '')
                if field_name in config:
                    try:
                        decrypted_config[field_name] = self.cipher.decrypt(
                            config[field_name].encode()
                        ).decode()
                    except Exception as e:
                        logger.error(
                            "Config field decryption failed for '%s': %s — "
                            "check MASTER_ENCRYPTION_KEY and stored ciphertext",
                            field_name, e,
                        )
                        raise
        
        return decrypted_config

def encrypt_password(password: str) -> str:
    """Utility function to encrypt password"""
    if not password:
        return ""
    
    manager = SecureConfigManager()
    return manager.cipher.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password: str) -> str:
    """Utility function to decrypt password"""
    if not encrypted_password:
        return ""

    manager = SecureConfigManager()
    try:
        return manager.cipher.decrypt(encrypted_password.encode()).decode()
    except Exception as e:
        logger.error(
            "SMTP credential decryption failed: %s — "
            "check MASTER_ENCRYPTION_KEY and stored ciphertext",
            e,
        )
        raise


# ─────────────────────────────────────────────────────────────────────────────
# HMAC-signed tracking / unsubscribe tokens
# ─────────────────────────────────────────────────────────────────────────────
# Token format (URL-safe base64, no padding):
#
#     base64url(payload).base64url(sig)
#
# where:
#   payload = f"{purpose}|{campaign_id}|{subscriber_id}|{exp_unix}"
#   sig     = HMAC-SHA256(JWT_SECRET, payload)[:24 bytes]   # truncated to keep URLs short
#
# - `purpose` ∈ {"o" (open), "c" (click), "u" (unsubscribe)} so a click token
#   can't be replayed as an unsubscribe and vice versa.
# - `exp_unix` is enforced on verify. After expiry, the token is rejected.
# - Tokens are stateless: no DB row required to verify. For unsubscribe we
#   additionally keep a DB row (created by routes.unsubscribe) to enforce
#   one-time-use and provide an audit trail; the HMAC verification happens
#   first and is the security boundary.
#
# Why HMAC and not JWT here?
#   These tokens go into millions of email URLs. JWT's JSON encoding bloats
#   the URL; a compact pipe-delimited payload + HMAC saves ~40 bytes per send
#   and is still tamper-proof under the same HS256 secret.

_TRACKING_SIG_BYTES = 24  # 192-bit truncated MAC — safe against forgery


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    # Pad back to a multiple of 4
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _tracking_secret() -> bytes:
    secret = settings.JWT_SECRET
    if not secret:
        raise RuntimeError("JWT_SECRET is required for tracking token signing")
    return secret.encode("utf-8")


def sign_tracking_token(
    purpose: str,
    campaign_id: str,
    subscriber_id: str,
    ttl_seconds: int = 60 * 60 * 24 * 90,  # 90 days
) -> str:
    """
    Mint a stateless HMAC-signed tracking token.

    Args:
        purpose: One of "o" (open pixel), "c" (click redirect), "u" (unsubscribe).
        campaign_id: String of the ObjectId. Single canonical form.
        subscriber_id: String of the ObjectId. Single canonical form.
        ttl_seconds: How long the token stays valid. Default 90 days — long
            enough that genuinely late opens still count, short enough that
            ancient leaked URLs eventually stop firing.

    Returns:
        URL-safe ASCII string in the form `<payload_b64>.<sig_b64>`.
    """
    if purpose not in ("o", "c", "u"):
        raise ValueError(f"Unknown tracking token purpose: {purpose!r}")

    exp = int(time.time()) + int(ttl_seconds)
    payload = f"{purpose}|{campaign_id}|{subscriber_id}|{exp}".encode("utf-8")
    sig = hmac.new(_tracking_secret(), payload, hashlib.sha256).digest()[
        :_TRACKING_SIG_BYTES
    ]
    return f"{_b64url_encode(payload)}.{_b64url_encode(sig)}"


def verify_tracking_token(
    token: str,
    expected_purpose: Optional[str] = None,
) -> Optional[Tuple[str, str, str, int]]:
    """
    Verify a tracking token.

    Returns (purpose, campaign_id, subscriber_id, exp_unix) on success,
    or None if the token is malformed, the signature doesn't match, the
    purpose doesn't match, or the token has expired.

    Constant-time comparison is used for the MAC check to avoid leaking
    timing oracles to a network attacker.
    """
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _b64url_decode(payload_b64)
        sig = _b64url_decode(sig_b64)
    except Exception:
        return None

    expected_sig = hmac.new(_tracking_secret(), payload, hashlib.sha256).digest()[
        :_TRACKING_SIG_BYTES
    ]
    if not hmac.compare_digest(sig, expected_sig):
        return None

    try:
        purpose, campaign_id, subscriber_id, exp_str = payload.decode("utf-8").split("|")
        exp = int(exp_str)
    except Exception:
        return None

    if expected_purpose is not None and purpose != expected_purpose:
        return None
    if int(time.time()) > exp:
        return None

    return purpose, campaign_id, subscriber_id, exp

