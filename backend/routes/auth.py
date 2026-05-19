# backend/routes/auth.py
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
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
)
from core.i18n import SUPPORTED_LANGUAGES, normalize_language
from core.timezone import is_valid_timezone, DEFAULT_TIMEZONE
from database import get_users_collection

logger = logging.getLogger(__name__)
router = APIRouter()


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


def _auth_response(user_doc: dict, token_version: int) -> dict:
    """Mint a fresh access/refresh pair and shape the standard auth response."""
    access, refresh = create_token_pair(
        user_id=str(user_doc["_id"]),
        email=user_doc["email"],
        token_version=token_version,
    )
    return {
        "token": access,                # back-compat (frontend reads `token`)
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": {
            "id": str(user_doc["_id"]),
            "name": user_doc.get("name"),
            "email": user_doc.get("email"),
        },
    }


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/register")
async def register(user: UserRegister):
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
        return _auth_response(user_doc, token_version=0)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Registration failed")


@router.post("/login")
async def login(user: UserLogin):
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

        return _auth_response(db_user, token_version=int(db_user.get("token_version", 0)))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/refresh")
async def refresh(body: RefreshRequest):
    """
    Exchange a refresh token for a new access token.

    Failure modes (all 401):
      - Token missing / invalid signature / expired
      - Wrong token type (an access token sent here is rejected)
      - User deleted / deactivated
      - token_version on user doc has been bumped (password change, email change,
        admin revoke) — old refresh token is dead
    """
    payload = decode_jwt_token(body.refresh_token, expected_type=TOKEN_TYPE_REFRESH)
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
    return {
        "token": new_access,
        "access_token": new_access,
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
async def logout(current_user: dict = Depends(get_current_user)):
    """
    Server-side logout: bump token_version so every issued token for this user
    is rejected on the next request (defends against stolen-token reuse after
    the client clears localStorage).
    """
    users_collection = get_users_collection()
    new_tv = int(current_user.get("token_version", 0)) + 1
    await users_collection.update_one(
        {"_id": ObjectId(current_user["_id"])},
        {"$set": {"token_version": new_tv, "updated_at": datetime.utcnow()}},
    )
    return {"message": "Logged out"}
