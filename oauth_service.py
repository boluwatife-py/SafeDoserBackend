"""
OAuth service for SafeDoser backend
Handles Google OAuth authentication flows
"""

import os
import logging
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from urllib.parse import urlencode, parse_qs
import json

import requests
from authlib.integrations.requests_client import OAuth2Session
from authlib.jose import jwt
from dotenv import load_dotenv

from database import Database
from auth import AuthService

load_dotenv()
logger = logging.getLogger(__name__)

class OAuthService:
    """OAuth service for handling Google authentication"""
    
    def __init__(self, db: Database):
        self.db = db
        self.auth_service = AuthService(db)
        
        # Google OAuth configuration
        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        
        # Frontend URL for redirects
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        
        # OAuth endpoints
        self.google_auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
        self.google_token_url = "https://oauth2.googleapis.com/token"
        self.google_userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        
        # OAuth scopes
        self.google_scopes = ["openid", "email", "profile"]
    
    def is_configured(self, provider: str) -> bool:
        """Check if OAuth provider is properly configured"""
        if provider == "google":
            return bool(self.google_client_id and self.google_client_secret)
        return False
    
    def generate_state(self) -> str:
        """Generate a secure state parameter for OAuth"""
        return secrets.token_urlsafe(32)
    
    def store_oauth_state(self, state: str, provider: str) -> bool:
        """Store OAuth state in database for verification"""
        try:
            expires_at = datetime.utcnow() + timedelta(minutes=10)  # 10 minute expiry
            
            state_data = {
                "state": state,
                "provider": provider,
                "expires_at": expires_at.isoformat(),
                "used": False,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Store in a simple table or cache - for now we'll use a simple in-memory store
            # In production, you'd want to store this in Redis or database
            if not hasattr(self, '_oauth_states'):
                self._oauth_states = {}
            
            self._oauth_states[state] = state_data
            return True
            
        except Exception as e:
            logger.error(f"Error storing OAuth state: {str(e)}")
            return False
    
    def verify_oauth_state(self, state: str, provider: str) -> bool:
        """Verify OAuth state parameter"""
        try:
            if not hasattr(self, '_oauth_states') or state not in self._oauth_states:
                return False
            
            state_data = self._oauth_states[state]
            
            # Check if state matches provider and hasn't been used
            if (state_data["provider"] != provider or 
                state_data["used"] or 
                datetime.fromisoformat(state_data["expires_at"]) < datetime.utcnow()):
                return False
            
            # Mark as used
            state_data["used"] = True
            return True
            
        except Exception as e:
            logger.error(f"Error verifying OAuth state: {str(e)}")
            return False
    
    def get_google_auth_url(self) -> tuple[str, str]:
        """Generate Google OAuth authorization URL"""
        if not self.is_configured("google"):
            raise ValueError("Google OAuth not configured")
        
        state = self.generate_state()
        self.store_oauth_state(state, "google")
        
        params = {
            "client_id": self.google_client_id,
            "redirect_uri": self.google_redirect_uri,
            "scope": " ".join(self.google_scopes),
            "response_type": "code",
            "state": state,
            "access_type": "offline",
            "prompt": "consent"
        }
        
        auth_url = f"{self.google_auth_url}?{urlencode(params)}"
        print(auth_url)
        return auth_url, state
    
    async def handle_google_callback(self, code: str, state: str) -> Dict[str, Any]:
        """Handle Google OAuth callback"""
        try:
            # Verify state
            if not self.verify_oauth_state(state, "google"):
                raise ValueError("Invalid or expired state parameter")
            
            # Exchange code for tokens
            token_data = {
                "client_id": self.google_client_id,
                "client_secret": self.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.google_redirect_uri
            }
            
            token_response = requests.post(self.google_token_url, data=token_data)
            token_response.raise_for_status()
            tokens = token_response.json()
            
            # Get user info
            headers = {"Authorization": f"Bearer {tokens['access_token']}"}
            user_response = requests.get(self.google_userinfo_url, headers=headers)
            user_response.raise_for_status()
            user_info = user_response.json()
            
            # Create or get user
            user_data = {
                "email": user_info["email"],
                "name": user_info["name"],
                "avatar_url": user_info.get("picture"),
                "email_verified": user_info.get("verified_email", True),
                "oauth_provider": "google",
                "oauth_id": user_info["id"]
            }
            
            user = await self.create_or_get_oauth_user(user_data)
            
            # Generate JWT tokens
            access_token = self.auth_service.create_access_token(user["id"])
            refresh_token = self.auth_service.create_refresh_token(user["id"])
            
            return {
                "user": user,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer"
            }
            
        except Exception as e:
            logger.error(f"Google OAuth callback error: {str(e)}")
            raise
    
    async def create_or_get_oauth_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or get user from OAuth data"""
        try:
            # Check if user exists by email
            existing_user = await self.auth_service.get_user_by_email(user_data["email"])
            
            if existing_user:
                # Update user with OAuth info if needed
                update_data = {}
                if not existing_user.get("email_verified") and user_data.get("email_verified"):
                    update_data["email_verified"] = True
                if user_data.get("avatar_url") and not existing_user.get("avatar_url"):
                    update_data["avatar_url"] = user_data["avatar_url"]
                
                if update_data:
                    await self.auth_service.update_user(existing_user["id"], update_data)
                    existing_user.update(update_data)
                
                return existing_user
            
            # Create new user
            # Generate a random password for OAuth users
            random_password = secrets.token_urlsafe(32)
            
            # Estimate age as 30 if not provided (OAuth doesn't typically provide age)
            age = 30
            
            new_user_data = {
                "email": user_data["email"],
                "password": random_password,  # Will be hashed by auth service
                "name": user_data["name"],
                "age": age,
                "avatar": user_data.get("avatar_url")
            }
            
            # Create user through auth service
            user = await self.auth_service.create_user_from_dict(new_user_data)
            
            # Update with OAuth-specific data
            oauth_update = {
                "email_verified": user_data.get("email_verified", True)
            }
            
            await self.auth_service.update_user(user["id"], oauth_update)
            user.update(oauth_update)
            
            return user
            
        except Exception as e:
            logger.error(f"Error creating/getting OAuth user: {str(e)}")
            raise
    
    def get_frontend_redirect_url(self, success: bool, **params) -> str:
        """Generate frontend redirect URL with parameters"""
        if success:
            # Redirect to main app
            return f"{self.frontend_url}/"
        else:
            # Redirect to login with error
            error_params = urlencode(params)
            return f"{self.frontend_url}/auth/login?{error_params}"