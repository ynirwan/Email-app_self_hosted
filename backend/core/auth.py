# backend/core/auth.py - Updated imports
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import JWTError, jwt
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from core.config import settings
from database import get_users_collection

SECRET_KEY = settings.JWT_SECRET
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_jwt_token(data: dict) -> str:
    try:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        logger.error(f"JWT token creation failed: {e}")
        raise

def decode_jwt_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.error(f"JWT token decode failed: {e}")
        return None

# ✅ If you have any database operations here, update them to use get_users_collection()
# Example (if you have any functions that were using get_database):
async def verify_user_exists(user_id: str) -> bool:
    try:
        users_collection = get_users_collection()  # ✅ Updated
        user = await users_collection.find_one({"_id": user_id})
        return user is not None
    except Exception as e:
        logger.error(f"User verification failed: {e}")
        return False

