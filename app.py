"""
SafeDoser Backend API
A comprehensive FastAPI backend for the SafeDoser medication management app.
"""

import os
import logging
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, validator
import uvicorn

# Import our modules
from database import Database, get_database
from auth import AuthService, get_current_user
from ai_service import AIService
from email_service import EmailService, EmailDeliveryResult
from token_service import TokenService
from oauth_service import OAuthService
from models import (
    UserCreate, UserLogin, UserResponse, UserUpdate,
    SupplementCreate, SupplementUpdate, SupplementResponse,
    SupplementLogCreate, SupplementLogUpdate, SupplementLogResponse, MarkCompletedRequest,
    ChatMessage, ChatResponse, ChatHistoryResponse,
    HealthResponse
)
from utils import setup_logging, handle_image_upload

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting SafeDoser Backend API...")
    
    # Initialize database
    db = Database()
    await db.initialize()
    
    # Initialize services
    ai_service = AIService()
    email_service = EmailService()
    token_service = TokenService(db)
    oauth_service = OAuthService(db)
    
    # Store in app state
    app.state.db = db
    app.state.ai_service = ai_service
    app.state.email_service = email_service
    app.state.token_service = token_service
    app.state.oauth_service = oauth_service
    
    # Log email service status
    email_config = email_service.get_configuration_status()
    if email_config["configured"]:
        logger.info("Email service configured successfully")
        # Test SMTP connection
        test_result = email_service.test_smtp_connection()
        if test_result.success:
            logger.info("SMTP connection test successful")
        else:
            logger.warning(f"SMTP connection test failed: {test_result.message}")
    else:
        logger.warning(f"Email service not configured. Missing: {', '.join(email_config['missing_config'])}")
    
    # Log OAuth service status
    oauth_google_configured = oauth_service.is_configured("google")
    
    if oauth_google_configured:
        logger.info("Google OAuth configured successfully")
    else:
        logger.warning("Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET")
    
    logger.info("SafeDoser Backend API started successfully!")
    
    yield
    
    # Cleanup
    logger.info("Shutting down SafeDoser Backend API...")
    await db.close()

# Create FastAPI app
app = FastAPI(
    title="SafeDoser API",
    description="Backend API for SafeDoser - Your Personal Medication Companion",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware - Allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    email_service = app.state.email_service
    oauth_service = app.state.oauth_service
    email_config = email_service.get_configuration_status()
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        gemini_configured=bool(os.getenv("GEMINI_API_KEY")),
        supabase_configured=bool(os.getenv("SUPABASE_URL")),
        email_configured=email_config["configured"]
    )

# Email configuration check endpoint
@app.get("/email/status")
async def email_status():
    """Get email service configuration status"""
    email_service = app.state.email_service
    config = email_service.get_configuration_status()
    
    # Test connection if configured
    if config["configured"]:
        test_result = email_service.test_smtp_connection()
        config["connection_test"] = {
            "success": test_result.success,
            "message": test_result.message,
            "error_code": test_result.error_code
        }
    
    return config

# OAuth endpoints
@app.get("/auth/google")
async def google_oauth(request: Request):
    """Initiate Google OAuth flow"""
    try:
        oauth_service = app.state.oauth_service
        
        if not oauth_service.is_configured("google"):
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Google OAuth not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables."
            )
        
        # Generate OAuth URL
        auth_url, state = oauth_service.get_google_auth_url()
        
        # Redirect to Google OAuth
        return RedirectResponse(url=auth_url, status_code=302)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google OAuth error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth initialization failed"
        )

@app.get("/auth/google/callback")
async def google_oauth_callback(code: str, state: str, error: Optional[str] = None):
    """Handle Google OAuth callback"""
    try:
        oauth_service = app.state.oauth_service
        
        if error:
            logger.warning(f"Google OAuth error: {error}")
            redirect_url = oauth_service.get_frontend_redirect_url(
                success=False, 
                error="oauth_error", 
                message="Google authentication was cancelled or failed"
            )
            return RedirectResponse(url=redirect_url, status_code=302)
        
        if not code or not state:
            redirect_url = oauth_service.get_frontend_redirect_url(
                success=False, 
                error="missing_parameters", 
                message="Missing required OAuth parameters"
            )
            return RedirectResponse(url=redirect_url, status_code=302)
        
        # Handle OAuth callback
        result = await oauth_service.handle_google_callback(code, state)
        
        # Create success redirect with tokens
        redirect_url = oauth_service.get_frontend_redirect_url(
            success=True,
            access_token=result['access_token'],
            refresh_token=result['refresh_token']
        )
        return RedirectResponse(url=redirect_url, status_code=302)
        
    except Exception as e:
        logger.error(f"Google OAuth callback error: {str(e)}")
        oauth_service = app.state.oauth_service
        redirect_url = oauth_service.get_frontend_redirect_url(
            success=False, 
            error="oauth_callback_failed", 
            message="Authentication failed. Please try again."
        )
        return RedirectResponse(url=redirect_url, status_code=302)

# Email verification models
class EmailVerificationRequest(BaseModel):
    email: EmailStr
    token: str

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    email: EmailStr
    token: str
    new_password: str

# Authentication endpoints
@app.post("/auth/signup", response_model=UserResponse)
async def signup(
    user_data: UserCreate,
    db: Database = Depends(get_database)
):
    """Create a new user account with email verification"""
    auth_service = AuthService(db)
    email_service = app.state.email_service
    token_service = app.state.token_service
    
    try:
        logger.info(f"Signup attempt for email: {user_data.email}")
        
        # Check if user already exists
        existing_user = await auth_service.get_user_by_email(user_data.email)
        if existing_user:
            logger.warning(f"Signup failed: Email already registered - {user_data.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{user_data.email}' is already registered."
            )
        
        # Create user (will be unverified initially)
        user = await auth_service.create_user(user_data)
        logger.info(f"User created successfully: {user['id']}")
        
        # Generate verification token
        verification_token = token_service.generate_token(user_data.email, "email_verification")
        
        # Store verification token
        token_stored = await token_service.store_verification_token(user_data.email, verification_token)
        
        if not token_stored:
            logger.error(f"Failed to store verification token for {user_data.email}")
        
        # Send verification email
        email_result = await email_service.send_verification_email(
            user_data.email, 
            user_data.name, 
            verification_token
        )
        
        # Generate tokens (user can use app but some features may be limited)
        access_token = auth_service.create_access_token(user["id"])
        refresh_token = auth_service.create_refresh_token(user["id"])

        response_data = {
            "user": user,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "email_sent": email_result.success,
            "email_message": email_result.message
        }

        # Log email delivery status
        if email_result.success:
            logger.info(f"Verification email sent successfully to {user_data.email}")
        else:
            logger.warning(f"Failed to send verification email to {user_data.email}: {email_result.message}")

        return UserResponse(**response_data)
        
    except HTTPException as http_exc:
        logger.warning(f"Signup failed with HTTPException: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.error(f"Signup error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.post("/auth/verify-email")
async def verify_email(
    verification_data: EmailVerificationRequest,
    db: Database = Depends(get_database)
):
    """Verify user email address"""
    try:
        logger.info(f"Email verification attempt for: {verification_data.email}")
        
        token_service = app.state.token_service
        auth_service = AuthService(db)
        
        # Verify the token
        is_valid = await token_service.verify_token(
            verification_data.email, 
            verification_data.token, 
            "email_verification"
        )
        
        if not is_valid:
            logger.warning(f"Invalid verification token for {verification_data.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token"
            )
        
        # Update user as verified
        user = await auth_service.get_user_by_email(verification_data.email)
        
        if not user:
            logger.error(f"User not found during verification: {verification_data.email}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Mark user as verified using the auth service method
        verification_success = await auth_service.mark_email_verified(verification_data.email)
        
        if not verification_success:
            logger.error(f"Failed to mark email as verified for {verification_data.email}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify email"
            )
        
        logger.info(f"Email verified successfully for {verification_data.email}")
        return {"message": "Email verified successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Email verification failed"
        )

@app.post("/auth/resend-verification")
async def resend_verification_email(
    email_data: dict,
    db: Database = Depends(get_database)
):
    """Resend verification email"""
    try:
        email = email_data.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is required"
            )
        
        logger.info(f"Resend verification request for: {email}")
        
        auth_service = AuthService(db)
        email_service = app.state.email_service
        token_service = app.state.token_service
        
        # Check if user exists
        user = await auth_service.get_user_by_email(email)
        if not user:
            logger.warning(f"Resend verification failed: User not found - {email}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if already verified
        if user.get("email_verified", False):
            logger.warning(f"Resend verification failed: Email already verified - {email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already verified"
            )
        
        # Generate new verification token (this will invalidate previous ones)
        verification_token = token_service.generate_token(email, "email_verification")
        
        # Store verification token (this will invalidate previous ones)
        token_stored = await token_service.store_verification_token(email, verification_token)
        
        if not token_stored:
            logger.error(f"Failed to store verification token for {email}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate verification token"
            )
        
        # Send verification email
        email_result = await email_service.send_verification_email(
            email, 
            user["name"], 
            verification_token
        )
        
        if email_result.success:
            logger.info(f"Verification email resent successfully to {email} (previous tokens invalidated)")
            return {
                "message": "Verification email sent successfully",
                "email_sent": True
            }
        else:
            logger.error(f"Failed to resend verification email to {email}: {email_result.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send verification email: {email_result.message}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resend verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend verification email"
        )

@app.post("/auth/login", response_model=UserResponse)
async def login(
    credentials: UserLogin,
    db: Database = Depends(get_database)
):
    """Authenticate user and return tokens"""
    try:
        logger.info(f"Login attempt for email: {credentials.email}")
        
        auth_service = AuthService(db)
        
        # Authenticate user (this will check email verification)
        user = await auth_service.authenticate_user(
            credentials.email, 
            credentials.password
        )
        
        if not user:
            logger.warning(f"Login failed: Invalid credentials for {credentials.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Generate tokens
        access_token = auth_service.create_access_token(user["id"])
        refresh_token = auth_service.create_refresh_token(user["id"])
        
        logger.info(f"Login successful for user: {user['id']}")
        
        return UserResponse(
            user=user,
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@app.post("/auth/forgot-password")
async def forgot_password(
    request_data: PasswordResetRequest,
    db: Database = Depends(get_database)
):
    """Send password reset email"""
    try:
        logger.info(f"Password reset request for: {request_data.email}")
        
        auth_service = AuthService(db)
        email_service = app.state.email_service
        token_service = app.state.token_service
        
        # Check if user exists
        user = await auth_service.get_user_by_email(request_data.email)
        if not user:
            logger.warning(f"Password reset failed: User not found - {request_data.email}")
            # For security, always return success message
            return {
                "message": "If the email exists in our system, a reset link has been sent",
                "email_sent": False,
                "reason": "User not found"
            }
        
        # Generate reset token (this will invalidate previous ones)
        reset_token = token_service.generate_token(request_data.email, "password_reset")
        
        # Store reset token (this will invalidate previous ones)
        token_stored = await token_service.store_reset_token(request_data.email, reset_token)
        
        if not token_stored:
            logger.error(f"Failed to store reset token for {request_data.email}")
            return {
                "message": "If the email exists in our system, a reset link has been sent",
                "email_sent": False,
                "reason": "Token storage failed"
            }
        
        # Send reset email
        email_result = await email_service.send_password_reset_email(
            request_data.email,
            user["name"],
            reset_token
        )
        
        if email_result.success:
            logger.info(f"Password reset email sent successfully to {request_data.email} (previous tokens invalidated)")
            return {
                "message": "If the email exists in our system, a reset link has been sent",
                "email_sent": True
            }
        else:
            logger.error(f"Failed to send password reset email to {request_data.email}: {email_result.message}")
            return {
                "message": "If the email exists in our system, a reset link has been sent",
                "email_sent": False,
                "reason": email_result.message,
                "error_code": email_result.error_code
            }
        
    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        # For security, always return success message
        return {
            "message": "If the email exists in our system, a reset link has been sent",
            "email_sent": False,
            "reason": "Internal error"
        }

@app.post("/auth/reset-password")
async def reset_password(
    reset_data: PasswordResetConfirm,
    db: Database = Depends(get_database)
):
    """Reset user password with token"""
    try:
        logger.info(f"Password reset confirmation for: {reset_data.email}")
        
        auth_service = AuthService(db)
        token_service = app.state.token_service
        
        # Verify the reset token
        is_valid = await token_service.verify_token(
            reset_data.email,
            reset_data.token,
            "password_reset"
        )
        
        if not is_valid:
            logger.warning(f"Invalid reset token for {reset_data.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        
        # Get user
        user = await auth_service.get_user_by_email(reset_data.email)
        if not user:
            logger.error(f"User not found during password reset: {reset_data.email}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Update password
        await auth_service.update_user(user["id"], {"password": reset_data.new_password})
        
        logger.info(f"Password reset successfully for {reset_data.email}")
        return {"message": "Password reset successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset confirmation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed"
        )

@app.post("/auth/refresh")
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Database = Depends(get_database)
):
    """Refresh access token"""
    try:
        auth_service = AuthService(db)
        
        # Verify refresh token and get user
        user_id = auth_service.verify_refresh_token(credentials.credentials)
        user = await auth_service.get_user_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Generate new access token
        access_token = auth_service.create_access_token(user["id"])
        
        return {
            "access_token": access_token,
            "token_type": "bearer"
        }
        
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

# User profile endpoints
@app.get("/user/profile")
async def get_profile(
    current_user: dict = Depends(get_current_user)
):
    """Get current user profile"""
    return {"user": current_user}

@app.put("/user/profile")
async def update_profile(
    profile_data: UserUpdate,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Update user profile"""
    try:
        auth_service = AuthService(db)
        
        # Update user profile
        updated_user = await auth_service.update_user(
            current_user["id"], 
            profile_data.dict(exclude_unset=True)
        )
        
        return {"user": updated_user}
        
    except Exception as e:
        logger.error(f"Profile update error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )

# Supplement endpoints
@app.get("/supplements", response_model=List[SupplementResponse])
async def get_supplements(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Get user's supplements"""
    try:
        logger.debug(f"Getting supplements for user: {current_user['id']}")
        supplements = await db.get_user_supplements(current_user["id"])
        logger.debug(f"Found {len(supplements)} supplements")
        return supplements
        
    except Exception as e:
        logger.error(f"Get supplements error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch supplements"
        )

@app.post("/supplements", response_model=SupplementResponse)
async def create_supplement(
    supplement_data: SupplementCreate,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Create a new supplement"""
    try:
        logger.info(f"Creating supplement for user: {current_user['id']}")
        logger.debug(f"Supplement data received: {supplement_data.dict()}")
        
        supplement = await db.create_supplement(
            current_user["id"], 
            supplement_data.dict()
        )
        
        logger.info(f"Supplement created successfully: {supplement['id']}")
        return supplement
        
    except Exception as e:
        logger.error(f"Create supplement error: {str(e)}")
        logger.error(f"Supplement data that failed: {supplement_data.dict()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create supplement: {str(e)}"
        )

@app.put("/supplements/{supplement_id}", response_model=SupplementResponse)
async def update_supplement(
    supplement_id: int,
    supplement_data: SupplementUpdate,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Update a supplement"""
    try:
        logger.info(f"Updating supplement {supplement_id} for user: {current_user['id']}")
        logger.debug(f"Update data: {supplement_data.dict(exclude_unset=True)}")
        
        # Verify supplement belongs to user
        supplement = await db.get_supplement_by_id(supplement_id)
        if not supplement or supplement["user_id"] != current_user["id"]:
            logger.warning(f"Supplement not found or access denied: {supplement_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supplement not found"
            )
        
        # Update supplement
        updated_supplement = await db.update_supplement(
            supplement_id, 
            supplement_data.dict(exclude_unset=True)
        )
        
        logger.info(f"Supplement updated successfully: {supplement_id}")
        return updated_supplement
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update supplement error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update supplement"
        )

@app.delete("/supplements/{supplement_id}")
async def delete_supplement(
    supplement_id: int,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Delete a supplement"""
    try:
        logger.info(f"Deleting supplement {supplement_id} for user: {current_user['id']}")
        
        # Verify supplement belongs to user
        supplement = await db.get_supplement_by_id(supplement_id)
        if not supplement or supplement["user_id"] != current_user["id"]:
            logger.warning(f"Supplement not found or access denied: {supplement_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supplement not found"
            )
        
        # Delete supplement
        await db.delete_supplement(supplement_id)
        
        logger.info(f"Supplement deleted successfully: {supplement_id}")
        return {"message": "Supplement deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete supplement error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete supplement"
        )

# Supplement logs endpoints
@app.get("/supplement-logs/today")
async def get_today_supplement_logs(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Get today's supplement logs for the user"""
    try:
        logger.debug(f"Getting today's supplement logs for user: {current_user['id']}")
        
        today = date.today()
        logs = await db.get_supplement_logs_by_date(current_user["id"], today)
        
        logger.debug(f"Found {len(logs)} supplement logs for today")
        return logs
        
    except Exception as e:
        logger.error(f"Get today's supplement logs error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch today's supplement logs"
        )

@app.post("/supplement-logs/mark-completed")
async def mark_supplement_completed(
    log_data: MarkCompletedRequest,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Mark a supplement as completed for a specific time"""
    try:
        logger.info(f"Marking supplement {log_data.supplement_id} as {log_data.status} at {log_data.scheduled_time} for user: {current_user['id']}")
        
        # Verify supplement belongs to user
        supplement = await db.get_supplement_by_id(log_data.supplement_id)
        if not supplement or supplement["user_id"] != current_user["id"]:
            logger.warning(f"Supplement not found or access denied: {log_data.supplement_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supplement not found"
            )
        
        # Check if log already exists for today
        today = date.today()
        existing_log = await db.get_supplement_log_by_supplement_and_time(
            current_user["id"], 
            log_data.supplement_id, 
            log_data.scheduled_time, 
            today
        )
        
        if existing_log:
            # Update existing log
            update_data = {
                "status": log_data.status,
                "notes": log_data.notes
            }
            
            if log_data.status == "taken":
                update_data["taken_at"] = datetime.utcnow()
            
            updated_log = await db.update_supplement_log(existing_log["id"], update_data)
            logger.info(f"Updated existing supplement log: {existing_log['id']}")
            return updated_log
        else:
            # Create new log
            log_create_data = {
                "user_id": current_user["id"],
                "supplement_id": log_data.supplement_id,
                "scheduled_time": log_data.scheduled_time,
                "status": log_data.status,
                "notes": log_data.notes
            }
            
            if log_data.status == "taken":
                log_create_data["taken_at"] = datetime.utcnow()
            
            new_log = await db.create_supplement_log(log_create_data)
            logger.info(f"Created new supplement log: {new_log['id']}")
            return new_log
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mark supplement completed error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark supplement as completed"
        )

@app.put("/supplement-logs/{log_id}")
async def update_supplement_log(
    log_id: str,
    log_data: SupplementLogUpdate,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Update a supplement log"""
    try:
        logger.info(f"Updating supplement log {log_id} for user: {current_user['id']}")
        
        # Verify log belongs to user
        log = await db.get_supplement_log_by_id(log_id)
        if not log or log["user_id"] != current_user["id"]:
            logger.warning(f"Supplement log not found or access denied: {log_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supplement log not found"
            )
        
        # Prepare update data
        update_data = log_data.dict(exclude_unset=True)
        
        # Set taken_at timestamp if status is being changed to taken
        if log_data.status == "taken" and log.get("status") != "taken":
            update_data["taken_at"] = datetime.utcnow()
        elif log_data.status and log_data.status != "taken":
            update_data["taken_at"] = None
        
        updated_log = await db.update_supplement_log(log_id, update_data)
        
        logger.info(f"Supplement log updated successfully: {log_id}")
        return updated_log
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update supplement log error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update supplement log"
        )

# Chat endpoints
@app.post("/chat", response_model=ChatResponse)
async def send_chat_message(
    message_data: ChatMessage,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Send a chat message and get AI response"""
    try:
        logger.debug(f"Chat message from user {current_user['id']}: {message_data.message[:50]}...")
        
        ai_service = app.state.ai_service
        
        # Get user's supplements for context
        supplements = await db.get_user_supplements(current_user["id"])
        
        # Get recent chat history
        chat_history = await db.get_chat_history(current_user["id"], limit=10)
        
        # Prepare context for AI
        context = {
            "user_name": current_user["name"],
            "user_age": current_user["age"],
            "supplements": supplements,
            "current_time": datetime.utcnow().isoformat()
        }
        
        # Generate AI response
        ai_response = await ai_service.generate_response(
            message_data.message,
            context,
            chat_history
        )
        
        # Save user message
        await db.save_chat_message(
            current_user["id"],
            "user",
            message_data.message,
            context
        )
        
        # Save AI response
        await db.save_chat_message(
            current_user["id"],
            "assistant",
            ai_response,
            context
        )
        
        logger.debug(f"Chat response generated for user {current_user['id']}")
        return ChatResponse(reply=ai_response)
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        
        # Return fallback response
        fallback_response = (
            "I'm experiencing some technical difficulties right now, but I'm still here to help! 🔧\n\n"
            "For immediate medical questions, please contact your healthcare provider. "
            "For general supplement information, you can also check reliable sources like your pharmacist "
            "or trusted medical websites.\n\n"
            "I'll be back to full functionality soon. Thank you for your patience! 💊"
        )
        
        return ChatResponse(reply=fallback_response)

@app.get("/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Get chat history"""
    try:
        logger.debug(f"Getting chat history for user {current_user['id']}, limit: {limit}")
        messages = await db.get_chat_history(current_user["id"], limit)
        return ChatHistoryResponse(messages=messages)
        
    except Exception as e:
        logger.error(f"Get chat history error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch chat history"
        )

@app.delete("/chat/clear")
async def clear_chat_history(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Clear chat history"""
    try:
        logger.info(f"Clearing chat history for user: {current_user['id']}")
        await db.clear_chat_history(current_user["id"])
        return {"message": "Chat history cleared successfully"}
        
    except Exception as e:
        logger.error(f"Clear chat history error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear chat history"
        )

# Image upload endpoint
@app.post("/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload an image file"""
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be an image"
            )
        
        # Handle image upload
        image_url = await handle_image_upload(file, current_user["id"])
        
        return {"image_url": image_url}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image upload error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload image"
        )

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )

# Run the application
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENVIRONMENT") == "development"
    )