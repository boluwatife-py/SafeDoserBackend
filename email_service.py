"""
Email service for SafeDoser backend
Handles email verification and password reset emails
"""

import os
import logging
import smtplib
import secrets
import hashlib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class EmailService:
    """Email service for sending verification and reset emails"""
    
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("FROM_EMAIL", self.smtp_username)
        self.app_name = "SafeDoser"
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        
        # Check if email is configured
        self.is_configured = bool(self.smtp_username and self.smtp_password)
        
        if not self.is_configured:
            logger.warning("Email service not configured. Email features will be disabled.")
    
    def generate_verification_token(self, email: str) -> str:
        """Generate a secure verification token"""
        # Create a unique token using email + timestamp + random bytes
        timestamp = str(int(datetime.utcnow().timestamp()))
        random_bytes = secrets.token_hex(16)
        token_data = f"{email}:{timestamp}:{random_bytes}"
        
        # Hash the token data for security
        token = hashlib.sha256(token_data.encode()).hexdigest()
        return token
    
    def generate_reset_token(self, email: str) -> str:
        """Generate a secure password reset token"""
        return self.generate_verification_token(email)
    
    async def send_verification_email(self, email: str, name: str, token: str) -> bool:
        """Send email verification email"""
        if not self.is_configured:
            logger.warning("Email service not configured - skipping verification email")
            return False
        
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
            return False
    
    async def send_password_reset_email(self, email: str, name: str, token: str) -> bool:
        """Send password reset email"""
        if not self.is_configured:
            logger.warning("Email service not configured - skipping reset email")
            return False
        
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
            return False
    
    async def _send_email(self, to_email: str, subject: str, text_body: str, html_body: str) -> bool:
        """Send email using SMTP"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email or ""
            msg['To'] = to_email
            
            # Add text and HTML parts
            text_part = MIMEText(text_body, 'plain')
            html_part = MIMEText(html_body, 'html')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username or "", self.smtp_password or "")
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False