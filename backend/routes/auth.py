# backend/routes/auth.py
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel, EmailStr, validator
from core.auth import (
    hash_password,
    verify_password,
    create_jwt_token,
    decode_jwt_token,
    get_current_user,
)
from core.i18n import SUPPORTED_LANGUAGES, normalize_language
from core.timezone import is_valid_timezone, DEFAULT_TIMEZONE
from database import get_users_collection
from bson import ObjectId
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str


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
    new_password: str


@router.post("/register")
async def register(user: UserRegister):
    try:
        users_collection = get_users_collection()
        existing = await users_collection.find_one({"email": user.email})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists"
            )

        hashed = hash_password(user.password)
        user_doc = {
            "name": user.name,
            "email": user.email,
            "password": hashed,
            "created_at": datetime.utcnow(),
            "is_active": True,
            "timezone": DEFAULT_TIMEZONE,
            "language": "en",
        }
        result = await users_collection.insert_one(user_doc)
        token = create_jwt_token(
            {"user_id": str(result.inserted_id), "sub": user.email}
        )
        return {
            "token": token,
            "user": {
                "id": str(result.inserted_id),
                "name": user.name,
                "email": user.email,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login")
async def login(user: UserLogin):
    try:
        users_collection = get_users_collection()
        db_user = await users_collection.find_one({"email": user.email})
        if not db_user or not verify_password(user.password, db_user["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )

        token = create_jwt_token({"user_id": str(db_user["_id"]), "sub": user.email})
        return {
            "token": token,
            "user": {
                "id": str(db_user["_id"]),
                "name": db_user["name"],
                "email": db_user["email"],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@router.get("/me")
async def get_profile(current_user: dict = Depends(get_current_user)):
    """
    Return the current user profile. The dict includes timezone & language
    so the frontend can apply them globally without a second request.
    Defaults are filled in for older accounts that pre-date these fields.
    """
    current_user.setdefault("timezone", DEFAULT_TIMEZONE)
    current_user.setdefault("language", "en")
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
        await users_collection.update_one(
            {"_id": ObjectId(current_user["_id"])},
            {"$set": {**update_dict, "updated_at": datetime.utcnow()}},
        )
        return {"message": "Profile updated successfully", "updated": update_dict}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        new_hashed = hash_password(pw_data.new_password)
        await users_collection.update_one(
            {"_id": ObjectId(current_user["_id"])},
            {"$set": {"password": new_hashed, "updated_at": datetime.utcnow()}},
        )
        return {"message": "Password changed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password change failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))