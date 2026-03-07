from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel, EmailStr
from core.auth import hash_password, verify_password, create_jwt_token, decode_jwt_token
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

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

@router.post("/register")
async def register(user: UserRegister):
    try:
        users_collection = get_users_collection()
        existing = await users_collection.find_one({"email": user.email})
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")
        
        hashed = hash_password(user.password)
        user_doc = {
            "name": user.name, 
            "email": user.email, 
            "password": hashed,
            "created_at": datetime.utcnow(),
            "is_active": True,
            "timezone": "UTC",
            "language": "en"
        }
        result = await users_collection.insert_one(user_doc)
        token = create_jwt_token({"user_id": str(result.inserted_id), "sub": user.email})
        return {
            "token": token,
            "user": {"id": str(result.inserted_id), "name": user.name, "email": user.email}
        }
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login")
async def login(user: UserLogin):
    try:
        users_collection = get_users_collection()
        db_user = await users_collection.find_one({"email": user.email})
        if not db_user or not verify_password(user.password, db_user['password']):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
        token = create_jwt_token({"user_id": str(db_user["_id"]), "sub": user.email})
        return {
            "token": token,
            "user": {"id": str(db_user["_id"]), "name": db_user["name"], "email": db_user["email"]}
        }
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

@router.get("/me")
async def get_profile(request: Request):
    try:
        token = request.headers.get("Authorization")
        if not token or not token.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Unauthorized")
        data = decode_jwt_token(token.split(" ")[1])
        if not data:
            raise HTTPException(status_code=401, detail="Invalid token")

        users_collection = get_users_collection()
        user = await users_collection.find_one({"_id": ObjectId(data["user_id"])}, {"password": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user["_id"] = str(user["_id"])
        return user
    except Exception as e:
        logger.error(f"Profile fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch profile")

@router.put("/me")
async def update_profile(request: Request, user_data: UserUpdate):
    try:
        token = request.headers.get("Authorization")
        if not token or not token.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Unauthorized")
        data = decode_jwt_token(token.split(" ")[1])
        if not data:
            raise HTTPException(status_code=401, detail="Invalid token")

        users_collection = get_users_collection()
        update_dict = {k: v for k, v in user_data.dict().items() if v is not None}
        if not update_dict:
            raise HTTPException(status_code=400, detail="No data to update")

        await users_collection.update_one(
            {"_id": ObjectId(data["user_id"])},
            {"$set": {**update_dict, "updated_at": datetime.utcnow()}}
        )
        return {"message": "Profile updated successfully"}
    except Exception as e:
        logger.error(f"Profile update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/me/password")
async def change_password(request: Request, pw_data: PasswordChange):
    try:
        token = request.headers.get("Authorization")
        if not token or not token.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Unauthorized")
        data = decode_jwt_token(token.split(" ")[1])
        if not data:
            raise HTTPException(status_code=401, detail="Invalid token")

        users_collection = get_users_collection()
        user = await users_collection.find_one({"_id": ObjectId(data["user_id"])})
        if not user or not verify_password(pw_data.current_password, user["password"]):
            raise HTTPException(status_code=400, detail="Incorrect current password")

        new_hashed = hash_password(pw_data.new_password)
        await users_collection.update_one(
            {"_id": ObjectId(data["user_id"])},
            {"$set": {"password": new_hashed, "updated_at": datetime.utcnow()}}
        )
        return {"message": "Password changed successfully"}
    except Exception as e:
        logger.error(f"Password change failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
