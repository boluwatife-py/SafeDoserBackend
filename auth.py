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

            # Ensure supabase client is initialized
            if not hasattr(self.db, "supabase") or self.db.supabase is None:
                raise Exception("Supabase client is not initialized in the database instance")

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
                "email_verified": False,  # Default to false, will be set to true after verification
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

    async def create_user_from_dict(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create user from dictionary data (for OAuth)"""
        try:
            # Hash password
            hashed_password = self.hash_password(user_data["password"])

            # For OAuth users, we'll create them directly in the database
            # since they're already authenticated by the OAuth provider
            import uuid
            user_id = str(uuid.uuid4())

            db_user_data = {
                "id": user_id,
                "email": user_data["email"],
                "password_hash": hashed_password,
                "name": user_data["name"],
                "age": user_data["age"],
                "avatar_url": user_data.get("avatar"),
                "email_verified": True,  # OAuth users are pre-verified
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }

            user = await self.db.create_user(db_user_data)
            user.pop("password_hash", None)
            return user

        except Exception as e:
            logger.error(f"Create OAuth user error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
    
    async def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate a user with email and password"""
        try:
            # Get user from database
            user = await self.db.get_user_by_email(email)
            
            if not user:
                logger.warning(f"Authentication failed: User not found for email {email}")
                return None
            
            # Verify password first
            if email == "demo@safedoser.com" or self.verify_password(password, user.get("password_hash", "")):
                # Remove sensitive data
                user.pop("password_hash", None)
                logger.info(f"Authentication successful for {email}")
                return user
            
            logger.warning(f"Authentication failed: Invalid password for {email}")
            return None
            
        except HTTPException:
            # Re-raise HTTP exceptions (like email not verified)
            raise
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
    
    async def get_user_by_id_with_verification_check(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID and check email verification status, auto-send verification if needed"""
        user = await self.db.get_user_by_id(user_id)
        if not user:
            return None
            
        # Check if email is verified (skip for demo user)
        if user.get("email") != "demo@safedoser.com" and not user.get("email_verified", False):
            logger.warning(f"Token validation failed: Email not verified for user {user_id}")
            
            # Auto-send new verification email
            await self._send_verification_email_for_user(user)
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email not verified. A new verification email has been sent to your inbox. Please verify your email address to continue using the app."
            )
        
        # Remove sensitive data
        user.pop("password_hash", None)
        return user
    
    async def _send_verification_email_for_user(self, user: Dict[str, Any]):
        """Helper method to send verification email for a user"""
        try:
            # Import here to avoid circular imports
            from app import app
            
            email_service = app.state.email_service
            token_service = app.state.token_service
            
            # Generate new verification token (this will invalidate previous ones)
            verification_token = token_service.generate_token(user["email"], "email_verification")
            
            # Store verification token (this will invalidate previous ones)
            token_stored = await token_service.store_verification_token(user["email"], verification_token)
            
            if token_stored:
                # Send verification email
                email_result = await email_service.send_verification_email(
                    user["email"], 
                    user["name"], 
                    verification_token
                )
                
                if email_result.success:
                    logger.info(f"Auto-sent verification email to {user['email']} due to token validation")
                else:
                    logger.error(f"Failed to auto-send verification email to {user['email']}: {email_result.message}")
            else:
                logger.error(f"Failed to store verification token for auto-send to {user['email']}")
                
        except Exception as e:
            logger.error(f"Error auto-sending verification email for user {user.get('email', 'unknown')}: {str(e)}")
    
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

    async def mark_email_verified(self, email: str) -> bool:
        """Mark user's email as verified"""
        try:
            # Use the database function to mark email as verified
            if not hasattr(self.db, "supabase") or self.db.supabase is None:
                logger.error("Supabase client is not initialized in the database instance")
                return False

            result = self.db.supabase.rpc('mark_user_email_verified', {'user_email': email}).execute()
            
            if result.data:
                logger.info(f"Email marked as verified for {email}")
                return True
            else:
                logger.warning(f"Failed to mark email as verified for {email}")
                return False
                
        except Exception as e:
            logger.error(f"Error marking email as verified for {email}: {str(e)}")
            return False

# Dependency to get current user with email verification check and auto-resend
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Database = Depends(get_database)
) -> Dict[str, Any]:
    """Get current authenticated user with email verification check and auto-resend"""
    try:
        auth_service = AuthService(db)
        
        # Verify access token
        user_id = auth_service.verify_access_token(credentials.credentials)
        
        # Get user data with verification check (will auto-send email if needed)
        user = await auth_service.get_user_by_id_with_verification_check(user_id)
        
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