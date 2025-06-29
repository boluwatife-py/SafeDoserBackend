"""
Token service for SafeDoser backend
Handles email verification and password reset tokens
"""

import os
import logging
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class TokenService:
    """Service for managing verification and reset tokens"""
    
    def __init__(self, db):
        self.db = db
        self.secret_key = os.getenv("JWT_SECRET_KEY", "default-secret-key")
    
    def generate_token(self, email: str, token_type: str) -> str:
        """Generate a secure token for email verification or password reset"""
        timestamp = str(int(datetime.utcnow().timestamp()))
        random_bytes = secrets.token_hex(16)
        token_data = f"{email}:{token_type}:{timestamp}:{random_bytes}:{self.secret_key}"
        
        # Hash the token data for security
        token = hashlib.sha256(token_data.encode()).hexdigest()
        return token
    
    async def store_verification_token(self, email: str, token: str) -> bool:
        """Store email verification token in database (invalidates previous tokens)"""
        try:
            # First, invalidate any existing verification tokens for this email
            await self._invalidate_existing_tokens(email, "email_verification")
            
            expires_at = datetime.utcnow() + timedelta(hours=24)  # 24 hour expiry
            
            token_data = {
                "email": email,
                "token": token,
                "token_type": "email_verification",
                "expires_at": expires_at.isoformat(),
                "used": False,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Store in verification_tokens table
            result = self.db.supabase.table("verification_tokens").insert(token_data).execute()
            
            if result.data:
                logger.info(f"Verification token stored for {email} (previous tokens invalidated)")
                return True
            else:
                logger.error(f"Failed to store verification token for {email}")
                return False
                
        except Exception as e:
            logger.error(f"Error storing verification token for {email}: {str(e)}")
            return False
    
    async def store_reset_token(self, email: str, token: str) -> bool:
        """Store password reset token in database (invalidates previous tokens)"""
        try:
            expires_at = datetime.utcnow() + timedelta(hours=1)  # 1 hour expiry
            
            # Invalidate any existing reset tokens for this email
            await self._invalidate_existing_tokens(email, "password_reset")
            
            token_data = {
                "email": email,
                "token": token,
                "token_type": "password_reset",
                "expires_at": expires_at.isoformat(),
                "used": False,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Store in verification_tokens table
            result = self.db.supabase.table("verification_tokens").insert(token_data).execute()
            
            if result.data:
                logger.info(f"Reset token stored for {email} (previous tokens invalidated)")
                return True
            else:
                logger.error(f"Failed to store reset token for {email}")
                return False
                
        except Exception as e:
            logger.error(f"Error storing reset token for {email}: {str(e)}")
            return False
    
    async def verify_token(self, email: str, token: str, token_type: str) -> bool:
        """Verify and consume a token"""
        try:
            # Get token from database
            result = self.db.supabase.table("verification_tokens").select("*").eq("email", email).eq("token", token).eq("token_type", token_type).eq("used", False).execute()
            
            if not result.data:
                logger.warning(f"Token not found or already used for {email}")
                return False
            
            token_record = result.data[0]
            
            # Check if token has expired
            expires_at = datetime.fromisoformat(token_record["expires_at"].replace('Z', '+00:00'))
            if datetime.utcnow().replace(tzinfo=expires_at.tzinfo) > expires_at:
                logger.warning(f"Token expired for {email}")
                return False
            
            # Mark token as used (atomic operation to prevent race conditions)
            update_result = self.db.supabase.table("verification_tokens").update({
                "used": True, 
                "used_at": datetime.utcnow().isoformat()
            }).eq("id", token_record["id"]).eq("used", False).execute()  # Double-check it's still unused
            
            if update_result.data:
                logger.info(f"Token verified and consumed for {email}")
                return True
            else:
                logger.warning(f"Token was already used by another request for {email}")
                return False
                
        except Exception as e:
            logger.error(f"Error verifying token for {email}: {str(e)}")
            return False
    
    async def _invalidate_existing_tokens(self, email: str, token_type: str):
        """Invalidate existing tokens of the same type for an email"""
        try:
            # Mark all existing unused tokens as used
            result = self.db.supabase.table("verification_tokens").update({
                "used": True, 
                "used_at": datetime.utcnow().isoformat()
            }).eq("email", email).eq("token_type", token_type).eq("used", False).execute()
            
            if result.data:
                logger.info(f"Invalidated {len(result.data)} existing {token_type} tokens for {email}")
            else:
                logger.info(f"No existing {token_type} tokens to invalidate for {email}")
                
        except Exception as e:
            logger.error(f"Error invalidating existing tokens for {email}: {str(e)}")
    
    async def cleanup_expired_tokens(self):
        """Clean up expired tokens (should be run periodically)"""
        try:
            current_time = datetime.utcnow().isoformat()
            result = self.db.supabase.table("verification_tokens").delete().lt("expires_at", current_time).execute()
            
            if result.data:
                logger.info(f"Cleaned up {len(result.data)} expired tokens")
            else:
                logger.info("No expired tokens to clean up")
                
        except Exception as e:
            logger.error(f"Error cleaning up expired tokens: {str(e)}")
    
    async def has_valid_verification_token(self, email: str) -> bool:
        """Check if user has a valid (unused, non-expired) verification token"""
        try:
            current_time = datetime.utcnow().isoformat()
            result = self.db.supabase.table("verification_tokens").select("id").eq("email", email).eq("token_type", "email_verification").eq("used", False).gt("expires_at", current_time).execute()
            
            return len(result.data) > 0
            
        except Exception as e:
            logger.error(f"Error checking for valid verification token for {email}: {str(e)}")
            return False