from fastapi import APIRouter, HTTPException, Depends, Request, status
from models.user_model import UserInDB
from schemas.user_schema import UserRegister, UserLogin
from core.auth import hash_password, verify_password, create_jwt_token, decode_jwt_token
from database import get_users_collection  # ✅ Use AsyncIOMotorClient collection getter
from bson import ObjectId
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/register")
async def register(user: UserRegister):
    try:
        # ✅ Use AsyncIOMotorClient collection getter
        users_collection = get_users_collection()
        
        # ✅ Async database operation with proper error handling
        existing = await users_collection.find_one({"email": user.email})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="User already exists"
            )
        
        # ✅ Hash password and create user document
        hashed = hash_password(user.password)
        user_doc = {
            "name": user.name, 
            "email": user.email, 
            "password": hashed,
            "created_at": datetime.utcnow(),
            "is_active": True
        }
        
        # ✅ Async insert operation
        result = await users_collection.insert_one(user_doc)
        
        # ✅ Create JWT token with proper payload
        token = create_jwt_token({
            "user_id": str(result.inserted_id),
            "sub": user.email
        })
        
        logger.info(f"User registered successfully: {user.email}")
        
        return {
            "token": token,
            "user": {
                "id": str(result.inserted_id),
                "name": user.name,
                "email": user.email
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )

@router.post("/login")
async def login(user: UserLogin):
    try:
        # ✅ Use AsyncIOMotorClient collection getter
        users_collection = get_users_collection()
        
        # ✅ Async database operation
        db_user = await users_collection.find_one({"email": user.email})
        
        if not db_user or not verify_password(user.password, db_user['password']):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid credentials"
            )
        
        # ✅ Create JWT token with proper payload
        token = create_jwt_token({
            "user_id": str(db_user["_id"]),
            "sub": user.email
        })
        
        logger.info(f"User logged in successfully: {user.email}")
        
        return {
            "token": token,
            "user": {
                "id": str(db_user["_id"]),
                "name": db_user["name"],
                "email": db_user["email"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@router.get("/me")
async def get_profile(request: Request):
    try:
        # ✅ Extract and validate token
        token = request.headers.get("Authorization")
        if not token or not token.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Missing or invalid authorization header"
            )

        # ✅ Decode JWT token
        data = decode_jwt_token(token.split(" ")[1])
        if not data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid or expired token"
            )

        # ✅ Use AsyncIOMotorClient collection getter
        users_collection = get_users_collection()
        
        # ✅ Async database operation with projection to exclude password
        user = await users_collection.find_one(
            {"_id": ObjectId(data["user_id"])}, 
            {"password": 0}  # Exclude password from response
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="User not found"
            )

        # ✅ Convert ObjectId to string for JSON serialization
        user["_id"] = str(user["_id"])
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile fetch failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user profile"
        )

