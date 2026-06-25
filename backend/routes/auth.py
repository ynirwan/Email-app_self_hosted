# backend/routes/auth.py
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Response, status, Query
from pydantic import BaseModel, EmailStr, validator, Field
from bson import ObjectId
from datetime import datetime
import logging

from core.auth import (
    hash_password,
    verify_password,
    create_token_pair,
    create_access_token,
    decode_jwt_token,
    get_current_user,
    TOKEN_TYPE_REFRESH,
    COOKIE_ACCESS,
    COOKIE_REFRESH,
    COOKIE_SESSION_FLAG,
    ACCESS_TOKEN_EXPIRE_SECONDS,
    REFRESH_TOKEN_EXPIRE_SECONDS,
)
from core.i18n import SUPPORTED_LANGUAGES, normalize_language
from core.timezone import is_valid_timezone, DEFAULT_TIMEZONE
from core.license import get_license
from core.rate_limit import limiter
from database import get_users_collection

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Cookie helpers ─────────────────────────────────────────────────────────

def _is_secure(request: Request) -> bool:
    """True when the request arrived over HTTPS (or behind a trusted proxy)."""
    return (
        request.url.scheme == "https"
        or request.headers.get("X-Forwarded-Proto", "") == "https"
    )


def _set_auth_cookies(response: Response, request: Request, access: str, refresh: str) -> None:
    """Write the httpOnly JWT cookies and the JS-readable session flag."""
    secure = _is_secure(request)
    response.set_cookie(
        key=COOKIE_ACCESS,
        value=access,
        httponly=True,
        samesite="strict",
        secure=secure,
        max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
        path="/",
    )
    response.set_cookie(
        key=COOKIE_REFRESH,
        value=refresh,
        httponly=True,
        samesite="strict",
        secure=secure,
        max_age=REFRESH_TOKEN_EXPIRE_SECONDS,
        path="/api/auth/refresh",   # only sent to the refresh endpoint
    )
    # Non-httpOnly flag cookie — JS reads this to know a session is active without
    # being able to extract the actual JWT.
    response.set_cookie(
        key=COOKIE_SESSION_FLAG,
        value="1",
        httponly=False,
        samesite="strict",
        secure=secure,
        max_age=REFRESH_TOKEN_EXPIRE_SECONDS,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Expire all three auth cookies."""
    for name, path in [
        (COOKIE_ACCESS,        "/"),
        (COOKIE_REFRESH,       "/api/auth/refresh"),
        (COOKIE_SESSION_FLAG,  "/"),
    ]:
        response.delete_cookie(key=name, path=path)


# ── Request / response models ──────────────────────────────────────────────

class UserRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=200)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    timezone: Optional[str] = None
    language: Optional[str] = None

    @validator("timezone")
    def _check_tz(cls, v):
        if v is None:
            return v
        if not is_valid_timezone(v):
            raise ValueError("Invalid timezone. Use a valid IANA name like 'Europe/Berlin'.")
        return v

    @validator("language")
    def _check_lang(cls, v):
        if v is None:
            return v
        normalized = normalize_language(v)
        if normalized != v.strip().lower().split("-")[0]:
            raise ValueError(
                f"Unsupported language. Choose one of: {', '.join(SUPPORTED_LANGUAGES)}"
            )
        return normalized


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Helpers ────────────────────────────────────────────────────────────────

def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _auth_response(user_doc: dict, token_version: int, response: Response, request: Request) -> dict:
    """Mint a fresh access/refresh pair, set httpOnly cookies, return safe body."""
    access, refresh = create_token_pair(
        user_id=str(user_doc["_id"]),
        email=user_doc["email"],
        token_version=token_version,
    )
    _set_auth_cookies(response, request, access, refresh)
    # Body intentionally omits raw tokens — they are in httpOnly cookies.
    # The `token` field is kept for API clients that read it directly and have
    # not yet migrated; browser sessions should rely on the cookie.
    return {
        "token": access,                # API-client back-compat
        "token_type": "bearer",
        "user": {
            "id": str(user_doc["_id"]),
            "name": user_doc.get("name"),
            "email": user_doc.get("email"),
        },
    }


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/register")
@limiter.limit("5/minute")
async def register(request: Request, response: Response, user: UserRegister):
    """
    Public self-registration endpoint.

    Disabled by default in self-hosted deployments (REGISTRATION_ENABLED=false).
    Admin accounts are created during installation via install.py.
    Set REGISTRATION_ENABLED=true only if you explicitly want open sign-ups.
    """
    registration_enabled = os.getenv("REGISTRATION_ENABLED", "false").lower() == "true"
    if not registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Self-registration is disabled on this instance. "
                "Contact your administrator to get an account."
            ),
        )

    try:
        users_collection = get_users_collection()
        normalized_email = _normalize_email(user.email)

        existing = await users_collection.find_one({"email": normalized_email})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with that email already exists",
            )

        user_doc = {
            "name": user.name.strip(),
            "email": normalized_email,
            "password": hash_password(user.password),
            "created_at": datetime.utcnow(),
            "is_active": True,
            "token_version": 0,
            "timezone": DEFAULT_TIMEZONE,
            "language": "en",
        }
        result = await users_collection.insert_one(user_doc)
        user_doc["_id"] = result.inserted_id
        logger.info("New user registered via self-registration: %s", normalized_email)
        return _auth_response(user_doc, token_version=0, response=response, request=request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Registration failed")


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, response: Response, user: UserLogin):
    try:
        users_collection = get_users_collection()
        normalized_email = _normalize_email(user.email)
        db_user = await users_collection.find_one({"email": normalized_email})

        # Generic 401 — same message for "no such user" and "wrong password"
        # so we don't leak account existence.
        if not db_user or not verify_password(user.password, db_user["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if not db_user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated",
            )

        return _auth_response(db_user, token_version=int(db_user.get("token_version", 0)), response=response, request=request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/refresh")
async def refresh(request: Request, response: Response, body: Optional[RefreshRequest] = None):
    """
    Exchange a refresh token for a new access token.

    Token source (checked in order):
      1. httpOnly `refresh_token` cookie  (browser sessions)
      2. `refresh_token` field in the JSON body  (API clients / back-compat)

    Failure modes (all 401):
      - Token missing / invalid signature / expired
      - Wrong token type (an access token sent here is rejected)
      - User deleted / deactivated
      - token_version on user doc has been bumped (password change, email change,
        admin revoke) — old refresh token is dead
    """
    raw_refresh = (
        request.cookies.get(COOKIE_REFRESH)
        or (body.refresh_token if body else None)
    )
    if not raw_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    payload = decode_jwt_token(raw_refresh, expected_type=TOKEN_TYPE_REFRESH)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload",
        )

    users_collection = get_users_collection()
    try:
        db_user = await users_collection.find_one({"_id": ObjectId(user_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user reference in refresh token",
        )

    if not db_user or not db_user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account unavailable",
        )

    expected_tv = int(db_user.get("token_version", 0))
    if int(payload.get("tv", 0)) != expected_tv:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked — please log in again",
        )

    new_access = create_access_token(
        user_id=str(db_user["_id"]),
        email=db_user["email"],
        token_version=expected_tv,
    )
    secure = _is_secure(request)
    response.set_cookie(
        key=COOKIE_ACCESS,
        value=new_access,
        httponly=True,
        samesite="strict",
        secure=secure,
        max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
        path="/",
    )
    # Refresh the session flag TTL so the browser keeps the indicator alive.
    response.set_cookie(
        key=COOKIE_SESSION_FLAG,
        value="1",
        httponly=False,
        samesite="strict",
        secure=secure,
        max_age=REFRESH_TOKEN_EXPIRE_SECONDS,
        path="/",
    )
    return {
        "token": new_access,      # API-client back-compat
        "token_type": "bearer",
    }


@router.get("/me")
async def get_profile(current_user: dict = Depends(get_current_user)):
    """Return the current user profile (timezone & language defaulted)."""
    current_user.setdefault("timezone", DEFAULT_TIMEZONE)
    current_user.setdefault("language", "en")
    # Never leak internal-only fields to the client.
    current_user.pop("token_version", None)
    return current_user


@router.put("/me")
async def update_profile(
    user_data: UserUpdate,
    current_user: dict = Depends(get_current_user),
):
    try:
        users_collection = get_users_collection()
        update_dict = {k: v for k, v in user_data.dict().items() if v is not None}
        if not update_dict:
            raise HTTPException(status_code=400, detail="No data to update")

        # Email change requires uniqueness check + token revocation. Without
        # this, two accounts can end up with the same email AND a stolen
        # access token would survive an email swap.
        if "email" in update_dict:
            new_email = _normalize_email(update_dict["email"])
            update_dict["email"] = new_email
            if new_email != current_user.get("email"):
                existing = await users_collection.find_one(
                    {"email": new_email, "_id": {"$ne": ObjectId(current_user["_id"])}}
                )
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Email already in use",
                    )
                # Force re-auth: previously-issued tokens carry the old `tv`.
                update_dict["token_version"] = int(
                    current_user.get("token_version", 0)
                ) + 1

        if "name" in update_dict:
            update_dict["name"] = update_dict["name"].strip()

        update_dict["updated_at"] = datetime.utcnow()

        await users_collection.update_one(
            {"_id": ObjectId(current_user["_id"])},
            {"$set": update_dict},
        )

        return {
            "message": "Profile updated successfully",
            # Do not echo internal-only fields back.
            "updated": {k: v for k, v in update_dict.items() if k != "token_version"},
            "tokens_revoked": "token_version" in update_dict,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile update failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Profile update failed")


@router.put("/me/password")
async def change_password(
    pw_data: PasswordChange,
    current_user: dict = Depends(get_current_user),
):
    try:
        users_collection = get_users_collection()
        user = await users_collection.find_one({"_id": ObjectId(current_user["_id"])})
        if not user or not verify_password(pw_data.current_password, user["password"]):
            raise HTTPException(status_code=400, detail="Incorrect current password")

        if pw_data.current_password == pw_data.new_password:
            raise HTTPException(
                status_code=400, detail="New password must differ from current"
            )

        # Atomic: bump token_version in the same write that swaps the hash.
        # Every existing access AND refresh token signed for this user is
        # invalidated on the next request because their embedded `tv` no
        # longer matches.
        new_tv = int(user.get("token_version", 0)) + 1
        await users_collection.update_one(
            {"_id": ObjectId(current_user["_id"])},
            {
                "$set": {
                    "password": hash_password(pw_data.new_password),
                    "token_version": new_tv,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        # Mint a fresh pair so the caller doesn't get logged out mid-flow.
        access, refresh = create_token_pair(
            user_id=str(user["_id"]),
            email=user["email"],
            token_version=new_tv,
        )
        return {
            "message": "Password changed successfully",
            "token": access,
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password change failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Password change failed")


@router.post("/logout")
async def logout(response: Response, current_user: dict = Depends(get_current_user)):
    """
    Server-side logout: bump token_version so every issued token for this user
    is rejected on the next request, and clear all auth cookies.
    """
    users_collection = get_users_collection()
    new_tv = int(current_user.get("token_version", 0)) + 1
    await users_collection.update_one(
        {"_id": ObjectId(current_user["_id"])},
        {"$set": {"token_version": new_tv, "updated_at": datetime.utcnow()}},
    )
    _clear_auth_cookies(response)
    return {"message": "Logged out"}


# ── ZeniPost Dashboard — Admin Access ──────────────────────────────────────
# The ZeniPost Dashboard can generate a 15-minute super-admin token for managed
# customers.  The email-app registers this endpoint only when the license has
# admin_access_allowed=true.  The token is a JWT signed with ADMIN_ACCESS_SECRET
# (must match the value configured in the Dashboard).
#
# Flow:
#   1. Dashboard admin clicks "Access App" → Dashboard generates a JWT.
#   2. Admin opens: https://<customer-domain>/auth/admin-access?token=<jwt>
#   3. This endpoint verifies the token and issues a normal app session.
# ──────────────────────────────────────────────────────────────────────────

@router.get("/admin-access")
@limiter.limit("5/minute")
async def admin_access(request: Request, response: Response, token: str = Query(..., description="Admin access token issued by ZeniPost Dashboard")):
    """
    Verify a Dashboard-issued admin access token and create a super-admin session.

    Only available when the license has admin_access_allowed=true.
    Token expires in 15 minutes from issuance.
    """
    # Gate: only active when the license explicitly allows it
    lic = get_license()
    if not lic.valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="License invalid. Admin access unavailable.",
        )
    if not lic.admin_access_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is not enabled for this installation.",
        )

    # Verify the token
    from jose import jwt as jose_jwt, JWTError
    admin_secret = os.getenv("ADMIN_ACCESS_SECRET", "zenipost-admin-access-secret-2026")

    try:
        payload = jose_jwt.decode(token, admin_secret, algorithms=["HS256"])
    except JWTError as exc:
        logger.warning("Admin access token rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin access token.",
        )

    # Verify the token is for this domain
    token_domain = payload.get("domain", "")
    if token_domain and lic.domain and token_domain != lic.domain:
        logger.warning(
            "Admin access domain mismatch: token=%s license=%s",
            token_domain, lic.domain,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access token is not valid for this installation.",
        )

    if payload.get("type") != "zenipost_admin_access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
        )

    # Find or create the admin user account for this session
    # We look up a user with role="admin"; if none exists we reject — the
    # installation must have been set up via install.py first.
    users_collection = get_users_collection()
    admin_user = await users_collection.find_one(
        {"role": "admin"},
        sort=[("created_at", 1)],
    )
    if not admin_user:
        # Fallback: any active user (installation may not use role field)
        admin_user = await users_collection.find_one({"is_active": True})

    if not admin_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No admin account found on this installation.",
        )

    issued_by = payload.get("issued_by", "ZeniPost Dashboard")
    logger.info(
        "✅ Admin access granted — issued_by=%s domain=%s license_id=%s",
        issued_by, token_domain, payload.get("license_id"),
    )

    # Issue a short-lived access-only token for this admin session.
    # Deliberately omit the refresh token — admin-access sessions must expire
    # naturally and cannot be silently extended via /auth/refresh.
    access = create_access_token(
        user_id=str(admin_user["_id"]),
        email=admin_user["email"],
        token_version=int(admin_user.get("token_version", 0)),
    )

    # Set the access cookie but NOT the refresh cookie so the session expires.
    secure = _is_secure(request)
    response.set_cookie(
        key=COOKIE_ACCESS,
        value=access,
        httponly=True,
        samesite="strict",
        secure=secure,
        max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
        path="/",
    )
    response.set_cookie(
        key=COOKIE_SESSION_FLAG,
        value="1",
        httponly=False,
        samesite="strict",
        secure=secure,
        max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
        path="/",
    )

    return {
        "token":         access,         # API-client back-compat
        # refresh_token intentionally absent — admin sessions are short-lived
        "token_type":    "bearer",
        "admin_session": True,
        "issued_by":     issued_by,
        "user": {
            "id":    str(admin_user["_id"]),
            "name":  admin_user.get("name"),
            "email": admin_user.get("email"),
        },
    }
