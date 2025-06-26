"""
SafeDoser Backend API
A comprehensive FastAPI backend for the SafeDoser medication management app.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, validator
import uvicorn

# Import our modules
from database import Database, get_database
from auth import AuthService, get_current_user
from ai_service import AIService
from email_service import EmailService, EmailDeliveryResult
from token_service import TokenService
from models import (
    UserCreate, UserLogin, UserResponse, UserUpdate,
    SupplementCreate, SupplementUpdate, SupplementResponse,
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
    
    # Store in app state
    app.state.db = db
    app.state.ai_service = ai_service
    app.state.email_service = email_service
    app.state.token_service = token_service
    
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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://safedoser.netlify.app",
        "https://safedoser.vercel.app",
        # Add your frontend URLs here
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    email_service = app.state.email_service
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
        # Check if user already exists
        existing_user = await auth_service.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{user_data.email}' is already registered."
            )
        
        # Create user (will be unverified initially)
        user = await auth_service.create_user(user_data)
        
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
        token_service = app.state.token_service
        
        # Verify the token
        is_valid = await token_service.verify_token(
            verification_data.email, 
            verification_data.token, 
            "email_verification"
        )
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token"
            )
        
        # Update user as verified
        auth_service = AuthService(db)
        user = await auth_service.get_user_by_email(verification_data.email)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Mark user as verified
        await auth_service.update_user(user["id"], {"email_verified": True})
        
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
        
        auth_service = AuthService(db)
        email_service = app.state.email_service
        token_service = app.state.token_service
        
        # Check if user exists
        user = await auth_service.get_user_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if already verified
        if user.get("email_verified", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already verified"
            )
        
        # Generate new verification token
        verification_token = token_service.generate_token(email, "email_verification")
        
        # Store verification token
        token_stored = await token_service.store_verification_token(email, verification_token)
        
        if not token_stored:
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
            logger.info(f"Verification email resent successfully to {email}")
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
        auth_service = AuthService(db)
        
        # Authenticate user
        user = await auth_service.authenticate_user(
            credentials.email, 
            credentials.password
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Generate tokens
        access_token = auth_service.create_access_token(user["id"])
        refresh_token = auth_service.create_refresh_token(user["id"])
        
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
        auth_service = AuthService(db)
        email_service = app.state.email_service
        token_service = app.state.token_service
        
        # Check if user exists
        user = await auth_service.get_user_by_email(request_data.email)
        if not user:
            # For security, always return success message
            return {
                "message": "If the email exists in our system, a reset link has been sent",
                "email_sent": False,
                "reason": "User not found"
            }
        
        # Generate reset token
        reset_token = token_service.generate_token(request_data.email, "password_reset")
        
        # Store reset token
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
            logger.info(f"Password reset email sent successfully to {request_data.email}")
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
        auth_service = AuthService(db)
        token_service = app.state.token_service
        
        # Verify the reset token
        is_valid = await token_service.verify_token(
            reset_data.email,
            reset_data.token,
            "password_reset"
        )
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        
        # Get user
        user = await auth_service.get_user_by_email(reset_data.email)
        if not user:
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
        supplements = await db.get_user_supplements(current_user["id"])
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
        supplement = await db.create_supplement(
            current_user["id"], 
            supplement_data.dict()
        )
        return supplement
        
    except Exception as e:
        logger.error(f"Create supplement error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create supplement"
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
        # Verify supplement belongs to user
        supplement = await db.get_supplement_by_id(supplement_id)
        if not supplement or supplement["user_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supplement not found"
            )
        
        # Update supplement
        updated_supplement = await db.update_supplement(
            supplement_id, 
            supplement_data.dict(exclude_unset=True)
        )
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
        # Verify supplement belongs to user
        supplement = await db.get_supplement_by_id(supplement_id)
        if not supplement or supplement["user_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supplement not found"
            )
        
        # Delete supplement
        await db.delete_supplement(supplement_id)
        return {"message": "Supplement deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete supplement error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete supplement"
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