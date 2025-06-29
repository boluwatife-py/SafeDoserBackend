"""
Email service for SafeDoser backend
Handles email verification and password reset emails with real status reporting
"""

import os
import logging
import smtplib
import secrets
import hashlib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class EmailDeliveryResult:
    """Result object for email delivery attempts"""
    def __init__(self, success: bool, message: str, error_code: Optional[str] = None):
        self.success = success
        self.message = message
        self.error_code = error_code
        self.timestamp = datetime.utcnow()

class EmailService:
    """Email service for sending verification and reset emails with real status reporting"""
    
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("FROM_EMAIL", self.smtp_username)
        self.app_name = "SafeDoser"
        self.frontend_url = os.getenv("FRONTEND_URL", "https://safedoser.netlify.app")
        
        # Check if email is configured
        self.is_configured = bool(self.smtp_username and self.smtp_password)
        
        if not self.is_configured:
            logger.warning("Email service not configured. Email features will be disabled.")
    
    def get_configuration_status(self) -> Dict[str, Any]:
        """Get email service configuration status"""
        return {
            "configured": self.is_configured,
            "smtp_server": self.smtp_server if self.is_configured else None,
            "smtp_port": self.smtp_port if self.is_configured else None,
            "from_email": self.from_email if self.is_configured else None,
            "missing_config": self._get_missing_config()
        }
    
    def _get_missing_config(self) -> list:
        """Get list of missing configuration items"""
        missing = []
        if not self.smtp_username:
            missing.append("SMTP_USERNAME")
        if not self.smtp_password:
            missing.append("SMTP_PASSWORD")
        return missing
    
    def generate_verification_token(self, email: str) -> str:
        """Generate a secure verification token"""
        timestamp = str(int(datetime.utcnow().timestamp()))
        random_bytes = secrets.token_hex(16)
        token_data = f"{email}:{timestamp}:{random_bytes}"
        
        # Hash the token data for security
        token = hashlib.sha256(token_data.encode()).hexdigest()
        return token
    
    def generate_reset_token(self, email: str) -> str:
        """Generate a secure password reset token"""
        return self.generate_verification_token(email)
    
    async def send_verification_email(self, email: str, name: str, token: str) -> EmailDeliveryResult:
        """Send email verification email with real status reporting"""
        if not self.is_configured:
            return EmailDeliveryResult(
                success=False,
                message="Email service not configured. Please check SMTP settings.",
                error_code="EMAIL_NOT_CONFIGURED"
            )
        
        try:
            verification_url = f"{self.frontend_url}/auth/verify-email?token={token}&email={email}"
            
            subject = f"Welcome to {self.app_name} - Verify Your Email"
            
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Verify Your Email - {self.app_name}</title>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: white; }}
                    .header {{ background: linear-gradient(135deg, #08B5A6, #066B65); padding: 40px 30px; text-align: center; }}
                    .header h1 {{ color: white; margin: 0; font-size: 28px; font-weight: bold; }}
                    .content {{ padding: 40px 30px; }}
                    .welcome {{ font-size: 24px; color: #121417; margin-bottom: 20px; font-weight: 600; }}
                    .message {{ font-size: 16px; color: #6b7280; line-height: 1.6; margin-bottom: 30px; }}
                    .button {{ display: inline-block; background: linear-gradient(135deg, #08B5A6, #066B65); color: white; padding: 16px 32px; text-decoration: none; border-radius: 12px; font-weight: 600; font-size: 16px; margin: 20px 0; }}
                    .button:hover {{ background: linear-gradient(135deg, #066B65, #044A46); }}
                    .footer {{ background-color: #f8f9fa; padding: 30px; text-align: center; border-top: 1px solid #e9ecef; }}
                    .footer p {{ color: #6b7280; font-size: 14px; margin: 5px 0; }}
                    .security-note {{ background-color: #dbf5f2; border-left: 4px solid #08B5A6; padding: 15px; margin: 20px 0; border-radius: 4px; }}
                    .security-note p {{ color: #066B65; font-size: 14px; margin: 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>💊 {self.app_name}</h1>
                    </div>
                    <div class="content">
                        <h2 class="welcome">Welcome to {self.app_name}, {name}! 🎉</h2>
                        <p class="message">
                            Thank you for signing up for {self.app_name}, your personal medication companion. 
                            To get started and secure your account, please verify your email address by clicking the button below.
                        </p>
                        <div style="text-align: center;">
                            <a href="{verification_url}" class="button">Verify My Email Address</a>
                        </div>
                        <div class="security-note">
                            <p><strong>🔒 Security Note:</strong> This verification link will expire in 24 hours for your security. If you didn't create an account with {self.app_name}, please ignore this email.</p>
                        </div>
                        <p class="message">
                            Once verified, you'll be able to:
                            <br>• 📋 Track your medications and supplements
                            <br>• ⏰ Set up smart reminders
                            <br>• 🤖 Chat with our AI health assistant
                            <br>• 📊 Monitor your medication adherence
                        </p>
                        <p class="message">
                            If the button doesn't work, you can copy and paste this link into your browser:
                            <br><a href="{verification_url}" style="color: #08B5A6; word-break: break-all;">{verification_url}</a>
                        </p>
                    </div>
                    <div class="footer">
                        <p><strong>{self.app_name}</strong> - Your Personal Medication Companion</p>
                        <p>This email was sent to {email}</p>
                        <p>If you have any questions, please contact our support team.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            text_body = f"""
            Welcome to {self.app_name}, {name}!
            
            Thank you for signing up for {self.app_name}, your personal medication companion.
            
            To get started and secure your account, please verify your email address by visiting this link:
            {verification_url}
            
            This verification link will expire in 24 hours for your security.
            
            Once verified, you'll be able to track your medications, set up reminders, and chat with our AI health assistant.
            
            If you didn't create an account with {self.app_name}, please ignore this email.
            
            Best regards,
            The {self.app_name} Team
            """
            
            return await self._send_email(email, subject, text_body, html_body)
            
        except Exception as e:
            logger.error(f"Failed to send verification email to {email}: {str(e)}")
            return EmailDeliveryResult(
                success=False,
                message=f"Failed to send verification email: {str(e)}",
                error_code="EMAIL_SEND_FAILED"
            )
    
    async def send_password_reset_email(self, email: str, name: str, token: str) -> EmailDeliveryResult:
        """Send password reset email with real status reporting"""
        if not self.is_configured:
            return EmailDeliveryResult(
                success=False,
                message="Email service not configured. Please check SMTP settings.",
                error_code="EMAIL_NOT_CONFIGURED"
            )
        
        try:
            reset_url = f"{self.frontend_url}/auth/reset-password?token={token}&email={email}"
            
            subject = f"{self.app_name} - Password Reset Request"
            
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Password Reset - {self.app_name}</title>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: white; }}
                    .header {{ background: linear-gradient(135deg, #08B5A6, #066B65); padding: 40px 30px; text-align: center; }}
                    .header h1 {{ color: white; margin: 0; font-size: 28px; font-weight: bold; }}
                    .content {{ padding: 40px 30px; }}
                    .title {{ font-size: 24px; color: #121417; margin-bottom: 20px; font-weight: 600; }}
                    .message {{ font-size: 16px; color: #6b7280; line-height: 1.6; margin-bottom: 30px; }}
                    .button {{ display: inline-block; background: linear-gradient(135deg, #08B5A6, #066B65); color: white; padding: 16px 32px; text-decoration: none; border-radius: 12px; font-weight: 600; font-size: 16px; margin: 20px 0; }}
                    .button:hover {{ background: linear-gradient(135deg, #066B65, #044A46); }}
                    .footer {{ background-color: #f8f9fa; padding: 30px; text-align: center; border-top: 1px solid #e9ecef; }}
                    .footer p {{ color: #6b7280; font-size: 14px; margin: 5px 0; }}
                    .security-note {{ background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; border-radius: 4px; }}
                    .security-note p {{ color: #856404; font-size: 14px; margin: 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>💊 {self.app_name}</h1>
                    </div>
                    <div class="content">
                        <h2 class="title">Password Reset Request 🔐</h2>
                        <p class="message">
                            Hi {name},
                            <br><br>
                            We received a request to reset the password for your {self.app_name} account. 
                            If you made this request, click the button below to reset your password.
                        </p>
                        <div style="text-align: center;">
                            <a href="{reset_url}" class="button">Reset My Password</a>
                        </div>
                        <div class="security-note">
                            <p><strong>⚠️ Security Notice:</strong> This password reset link will expire in 1 hour for your security. If you didn't request a password reset, please ignore this email and your password will remain unchanged.</p>
                        </div>
                        <p class="message">
                            If the button doesn't work, you can copy and paste this link into your browser:
                            <br><a href="{reset_url}" style="color: #08B5A6; word-break: break-all;">{reset_url}</a>
                        </p>
                        <p class="message">
                            For your security, this link will only work once and expires in 1 hour.
                        </p>
                    </div>
                    <div class="footer">
                        <p><strong>{self.app_name}</strong> - Your Personal Medication Companion</p>
                        <p>This email was sent to {email}</p>
                        <p>If you have any questions, please contact our support team.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            text_body = f"""
            Password Reset Request - {self.app_name}
            
            Hi {name},
            
            We received a request to reset the password for your {self.app_name} account.
            
            If you made this request, visit this link to reset your password:
            {reset_url}
            
            This password reset link will expire in 1 hour for your security.
            
            If you didn't request a password reset, please ignore this email and your password will remain unchanged.
            
            Best regards,
            The {self.app_name} Team
            """
            
            return await self._send_email(email, subject, text_body, html_body)
            
        except Exception as e:
            logger.error(f"Failed to send password reset email to {email}: {str(e)}")
            return EmailDeliveryResult(
                success=False,
                message=f"Failed to send password reset email: {str(e)}",
                error_code="EMAIL_SEND_FAILED"
            )
    
    async def _send_email(self, to_email: str, subject: str, text_body: str, html_body: str) -> EmailDeliveryResult:
        """Send email using SMTP with detailed error reporting"""
        try:
            # Validate email configuration
            if not self.smtp_username or not self.smtp_password:
                return EmailDeliveryResult(
                    success=False,
                    message="SMTP credentials not configured",
                    error_code="SMTP_CREDENTIALS_MISSING"
                )
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email if self.from_email is not None else "no-reply@example.com"
            msg['To'] = to_email
            
            # Add text and HTML parts
            text_part = MIMEText(text_body, 'plain')
            html_part = MIMEText(html_body, 'html')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # Send email with detailed error handling
            try:
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    # Enable debug output for troubleshooting
                    server.set_debuglevel(0)
                    
                    # Start TLS encryption
                    try:
                        server.starttls()
                    except smtplib.SMTPException as e:
                        return EmailDeliveryResult(
                            success=False,
                            message=f"Failed to start TLS encryption: {str(e)}",
                            error_code="SMTP_TLS_FAILED"
                        )
                    
                    # Authenticate
                    try:
                        server.login(self.smtp_username, self.smtp_password)
                    except smtplib.SMTPAuthenticationError as e:
                        return EmailDeliveryResult(
                            success=False,
                            message=f"SMTP authentication failed: {str(e)}. Check your username and password.",
                            error_code="SMTP_AUTH_FAILED"
                        )
                    except smtplib.SMTPException as e:
                        return EmailDeliveryResult(
                            success=False,
                            message=f"SMTP login error: {str(e)}",
                            error_code="SMTP_LOGIN_ERROR"
                        )
                    
                    # Send the email
                    try:
                        refused = server.send_message(msg)
                        if refused:
                            return EmailDeliveryResult(
                                success=False,
                                message=f"Email was refused by some recipients: {refused}",
                                error_code="EMAIL_REFUSED"
                            )
                        else:
                            logger.info(f"Email sent successfully to {to_email}")
                            return EmailDeliveryResult(
                                success=True,
                                message=f"Email sent successfully to {to_email}"
                            )
                    except smtplib.SMTPRecipientsRefused as e:
                        return EmailDeliveryResult(
                            success=False,
                            message=f"All recipients were refused: {str(e)}",
                            error_code="RECIPIENTS_REFUSED"
                        )
                    except smtplib.SMTPSenderRefused as e:
                        return EmailDeliveryResult(
                            success=False,
                            message=f"Sender was refused: {str(e)}",
                            error_code="SENDER_REFUSED"
                        )
                    except smtplib.SMTPDataError as e:
                        return EmailDeliveryResult(
                            success=False,
                            message=f"SMTP data error: {str(e)}",
                            error_code="SMTP_DATA_ERROR"
                        )
                        
            except smtplib.SMTPConnectError as e:
                return EmailDeliveryResult(
                    success=False,
                    message=f"Failed to connect to SMTP server {self.smtp_server}:{self.smtp_port}: {str(e)}",
                    error_code="SMTP_CONNECT_FAILED"
                )
            except smtplib.SMTPServerDisconnected as e:
                return EmailDeliveryResult(
                    success=False,
                    message=f"SMTP server disconnected unexpectedly: {str(e)}",
                    error_code="SMTP_DISCONNECTED"
                )
            except Exception as e:
                return EmailDeliveryResult(
                    success=False,
                    message=f"Unexpected SMTP error: {str(e)}",
                    error_code="SMTP_UNEXPECTED_ERROR"
                )
                
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return EmailDeliveryResult(
                success=False,
                message=f"Email service error: {str(e)}",
                error_code="EMAIL_SERVICE_ERROR"
            )
    
    def test_smtp_connection(self) -> EmailDeliveryResult:
        """Test SMTP connection and authentication"""
        if not self.is_configured:
            return EmailDeliveryResult(
                success=False,
                message="Email service not configured",
                error_code="EMAIL_NOT_CONFIGURED"
            )
        
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.set_debuglevel(0)
                server.starttls()
                if self.smtp_username is None or self.smtp_password is None:
                    return EmailDeliveryResult(
                        success=False,
                        message="SMTP credentials not configured",
                        error_code="SMTP_CREDENTIALS_MISSING"
                    )
                server.login(self.smtp_username, self.smtp_password)
                
                return EmailDeliveryResult(
                    success=True,
                    message="SMTP connection and authentication successful"
                )
                
        except smtplib.SMTPAuthenticationError as e:
            return EmailDeliveryResult(
                success=False,
                message=f"SMTP authentication failed: {str(e)}",
                error_code="SMTP_AUTH_FAILED"
            )
        except smtplib.SMTPConnectError as e:
            return EmailDeliveryResult(
                success=False,
                message=f"Failed to connect to SMTP server: {str(e)}",
                error_code="SMTP_CONNECT_FAILED"
            )
        except Exception as e:
            return EmailDeliveryResult(
                success=False,
                message=f"SMTP test failed: {str(e)}",
                error_code="SMTP_TEST_FAILED"
            )