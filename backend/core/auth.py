# backend/core/auth.py
"""
JWT auth helpers.

Token model
-----------
* ACCESS  : short-lived (default 24h). Carries {user_id, sub, tv, typ:"access", exp}.
* REFRESH : long-lived (default 7d).   Carries {user_id, sub, tv, typ:"refresh", exp}.

`tv` = the user's current `token_version`. Bumping the user's token_version
(done on password change, email change, or admin revocation) invalidates every
issued token in one shot — the next request fails verification because the
embedded `tv` no longer matches the value stored in Mongo.

`is_active` is also checked on every request so a deactivated user is locked
out of an already-issued, not-yet-expired token within the next API call.
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple
import logging

from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.config import settings
from database import get_users_collection

logger = logging.getLogger(__name__)

SECRET_KEY = settings.JWT_SECRET
ALGORITHM = settings.JWT_ALGORITHM

# Access token: short-lived, sent on every API request.
ACCESS_TOKEN_EXPIRE_SECONDS = (
    int(settings.JWT_EXP) if settings.JWT_EXP > 60 else 86400
)
# Refresh token: long-lived, only used at /auth/refresh.
REFRESH_TOKEN_EXPIRE_SECONDS = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# Password hashing (bcrypt, work factor managed by passlib).
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ── Token mint / decode ─────────────────────────────────────────────────────

def _encode(payload: dict, ttl_seconds: int, token_type: str) -> str:
    body = dict(payload)
    body["exp"] = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    body["iat"] = datetime.utcnow()
    body["typ"] = token_type
    return jwt.encode(body, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: str, email: str, token_version: int = 0) -> str:
    return _encode(
        {"user_id": user_id, "sub": email, "tv": token_version},
        ACCESS_TOKEN_EXPIRE_SECONDS,
        TOKEN_TYPE_ACCESS,
    )


def create_refresh_token(user_id: str, email: str, token_version: int = 0) -> str:
    return _encode(
        {"user_id": user_id, "sub": email, "tv": token_version},
        REFRESH_TOKEN_EXPIRE_SECONDS,
        TOKEN_TYPE_REFRESH,
    )


def create_token_pair(user_id: str, email: str, token_version: int = 0) -> Tuple[str, str]:
    """Mint both tokens at once (used at login/register/refresh)."""
    return (
        create_access_token(user_id, email, token_version),
        create_refresh_token(user_id, email, token_version),
    )


# Back-compat shim for older imports — defaults to access token.
def create_jwt_token(data: dict) -> str:
    return _encode(
        dict(data),
        ACCESS_TOKEN_EXPIRE_SECONDS,
        TOKEN_TYPE_ACCESS,
    )


def decode_jwt_token(token: str, expected_type: Optional[str] = None) -> Optional[dict]:
    """
    Decode a JWT and (optionally) enforce its `typ` claim.

    Returns the decoded payload on success, or None if the token is invalid,
    expired, or of the wrong type. Callers must distinguish None vs payload.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        logger.info(f"JWT decode failed: {e}")
        return None

    if expected_type is not None and payload.get("typ") != expected_type:
        logger.info(
            f"JWT type mismatch: expected '{expected_type}', got '{payload.get('typ')}'"
        )
        return None

    return payload


# ── FastAPI dependency ──────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    """
    Resolve the authenticated user from a Bearer access token.

    Failure modes (all 401):
      - Missing / malformed bearer header
      - Token signature invalid / expired
      - Wrong token type (refresh tokens cannot be used here)
      - User record deleted
      - User deactivated (is_active == False)
      - Token version stale (password/email changed since issue)
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated — please log in",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_jwt_token(
        credentials.credentials, expected_type=TOKEN_TYPE_ACCESS
    )
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired or invalid — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from bson import ObjectId

    users_collection = get_users_collection()
    try:
        user = await users_collection.find_one(
            {"_id": ObjectId(user_id)}, {"password": 0}
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found — account may have been deleted",
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
        )

    # Token-version revocation: bumped on password change, email change, or
    # explicit admin revoke. An old token signed with a stale `tv` is rejected
    # even though its signature and expiry are still valid.
    expected_tv = int(user.get("token_version", 0))
    token_tv = int(payload.get("tv", 0))
    if token_tv != expected_tv:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked — please log in again",
        )

    user["_id"] = str(user["_id"])
    return user


async def verify_user_exists(user_id: str) -> bool:
    try:
        from bson import ObjectId

        users_collection = get_users_collection()
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        return user is not None
    except Exception as e:
        logger.error(f"User verification failed: {e}")
        return False
