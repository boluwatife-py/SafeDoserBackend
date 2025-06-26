"""
Authentication module for SafeDoser backend
Handles user authentication, JWT tokens, and password hashing
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import secrets

from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
import base64
from dotenv import load_dotenv

load_dotenv()

from database import Database, get_database

logger = logging.getLogger(__name__)

# Security configuration
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

class AuthService:
    """Authentication service for user management"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def hash_password(self, password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    def create_access_token(self, user_id: str) -> str:
        """Create an access token"""
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode = {
            "sub": user_id,
            "exp": expire,
            "type": "access"
        }
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    def create_refresh_token(self, user_id: str) -> str:
        """Create a refresh token"""
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode = {
            "sub": user_id,
            "exp": expire,
            "type": "refresh"
        }
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    def verify_token(self, token: str, token_type: str = "access") -> str:
        """Verify a JWT token and return user ID"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id: Optional[str] = payload.get("sub")
            token_type_claim: Optional[str] = payload.get("type")
            
            if user_id is None or token_type_claim != token_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token"
                )
            
            return user_id
            
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    
    def verify_access_token(self, token: str) -> str:
        """Verify an access token"""
        return self.verify_token(token, "access")
    
    def verify_refresh_token(self, token: str) -> str:
        """Verify a refresh token"""
        return self.verify_token(token, "refresh")
    
    async def create_user(self, user_data) -> Dict[str, Any]:
        try:
            # Hash password
            hashed_password = self.hash_password(user_data.password)

            # Sign up in Supabase auth
            auth_response = self.db.supabase.auth.sign_up({
                "email": user_data.email,
                "password": user_data.password  # plain password for auth
            })

            if not auth_response.user:
                raise Exception("Supabase auth signup failed")

            # Insert user data in users table
            db_user_data = {
                "id": auth_response.user.id,
                "email": user_data.email,
                "password_hash": hashed_password,
                "name": user_data.name,
                "age": user_data.age,
                "avatar_url": user_data.avatar,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }

            user = await self.db.create_user(db_user_data)
            user.pop("password_hash", None)
            return user

        except Exception as e:
            logger.error(f"Create user error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    
    async def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate a user with email and password"""
        try:
            # For now, we'll use a simple authentication method
            # In a real implementation, you would use Supabase auth
            user = await self.db.get_user_by_email(email)
            
            if not user:
                return None
            
            # For demo purposes, we'll accept any password for demo@safedoser.com
            if email == "demo@safedoser.com" or self.verify_password(password, user.get("password_hash", "")):
                # Remove sensitive data
                user.pop("password_hash", None)
                return user
            
            return None
            
        except Exception as e:
            logger.error(f"Authenticate user error: {str(e)}")
            return None
    
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        return await self.db.get_user_by_email(email)
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        user = await self.db.get_user_by_id(user_id)
        if user:
            # Remove sensitive data
            user.pop("password_hash", None)
        return user
    
    async def update_user(self, user_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update user data"""
        try:
            # Handle password update
            if "password" in update_data:
                update_data["password_hash"] = self.hash_password(update_data.pop("password"))
            
            # Handle avatar update
            if "avatar" in update_data:
                # In a real implementation, you would upload to storage
                update_data["avatar_url"] = update_data.pop("avatar")
            
            user = await self.db.update_user(user_id, update_data)
            
            # Remove sensitive data
            user.pop("password_hash", None)
            
            return user
            
        except Exception as e:
            logger.error(f"Update user error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user"
            )

# Dependency to get current user
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Database = Depends(get_database)
) -> Dict[str, Any]:
    """Get current authenticated user"""
    try:
        auth_service = AuthService(db)
        
        # Verify access token
        user_id = auth_service.verify_access_token(credentials.credentials)
        
        # Get user data
        user = await auth_service.get_user_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get current user error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

# Optional user dependency (doesn't raise error if not authenticated)
async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Database = Depends(get_database)
) -> Optional[Dict[str, Any]]:
    """Get current user if authenticated, otherwise return None"""
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None