import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
import json

from supabase import create_client, Client

logger = logging.getLogger(__name__)

load_dotenv()

class Database:
    """Database connection and operations manager"""
    
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        self.supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Supabase URL and key must be provided")
        
        # Initialize Supabase client
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
    
    async def initialize(self):
        """Initialize database connections"""
        try:
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {str(e)}")
            raise
    
    async def close(self):
        """Close database connections"""
        pass
    
    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = self.supabase.table("users").insert(user_data).execute()
            if result.data:
                return result.data[0]
            raise Exception("Failed to create user record")
        except Exception as e:
            logger.error(f"Create user error: {str(e)}")
            raise


    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        try:
            result = self.supabase.table("users").select("*").eq("email", email).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Get user by email error: {str(e)}")
            return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        try:
            result = self.supabase.table("users").select("*").eq("id", user_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Get user by ID error: {str(e)}")
            return None
    
    async def update_user(self, user_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update user data"""
        try:
            update_data["updated_at"] = datetime.utcnow().isoformat()
            
            result = self.supabase.table("users").update(update_data).eq("id", user_id).execute()
            
            if result.data:
                return result.data[0]
            else:
                raise Exception("Failed to update user")
                
        except Exception as e:
            logger.error(f"Update user error: {str(e)}")
            raise
    
    # Supplement operations
    async def get_user_supplements(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all supplements for a user"""
        try:
            result = self.supabase.table("supplements").select("*").eq("user_id", user_id).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Get user supplements error: {str(e)}")
            return []
    
    async def get_supplement_by_id(self, supplement_id: int) -> Optional[Dict[str, Any]]:
        """Get supplement by ID"""
        try:
            result = self.supabase.table("supplements").select("*").eq("id", supplement_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Get supplement by ID error: {str(e)}")
            return None
    
    async def create_supplement(self, user_id: str, supplement_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new supplement"""
        try:
            supplement_record = {
                "user_id": user_id,
                "name": supplement_data["name"],
                "brand": supplement_data["brand"],
                "dosage_form": supplement_data["dosage_form"],
                "dose_quantity": supplement_data["dose_quantity"],
                "dose_unit": supplement_data["dose_unit"],
                "frequency": supplement_data["frequency"],
                "times_of_day": json.dumps(supplement_data.get("times_of_day", {})),
                "interactions": json.dumps(supplement_data.get("interactions", [])),
                "remind_me": supplement_data.get("remind_me", True),
                "expiration_date": supplement_data["expiration_date"],
                "quantity": supplement_data["quantity"],
                "image_url": supplement_data.get("image_url"),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            result = self.supabase.table("supplements").insert(supplement_record).execute()
            
            if result.data:
                return result.data[0]
            else:
                raise Exception("Failed to create supplement")
                
        except Exception as e:
            logger.error(f"Create supplement error: {str(e)}")
            raise
    
    async def update_supplement(self, supplement_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update supplement data"""
        try:
            update_data["updated_at"] = datetime.utcnow().isoformat()
            
            # Handle JSON fields
            if "times_of_day" in update_data:
                update_data["times_of_day"] = json.dumps(update_data["times_of_day"])
            if "interactions" in update_data:
                update_data["interactions"] = json.dumps(update_data["interactions"])
            
            result = self.supabase.table("supplements").update(update_data).eq("id", supplement_id).execute()
            
            if result.data:
                return result.data[0]
            else:
                raise Exception("Failed to update supplement")
                
        except Exception as e:
            logger.error(f"Update supplement error: {str(e)}")
            raise
    
    async def delete_supplement(self, supplement_id: int):
        """Delete a supplement"""
        try:
            result = self.supabase.table("supplements").delete().eq("id", supplement_id).execute()
            
            if not result.data:
                raise Exception("Failed to delete supplement")
                
        except Exception as e:
            logger.error(f"Delete supplement error: {str(e)}")
            raise
    
    # Chat operations
    async def save_chat_message(
        self, 
        user_id: str, 
        sender: str, 
        message: str, 
        context: Optional[Dict[str, Any]] = None
    ):
        """Save a chat message"""
        try:
            message_record = {
                "user_id": user_id,
                "sender": sender,
                "message": message,
                "context": json.dumps(context) if context else None,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            result = self.supabase.table("chat_messages").insert(message_record).execute()
            
            if not result.data:
                raise Exception("Failed to save chat message")
                
        except Exception as e:
            logger.error(f"Save chat message error: {str(e)}")
            raise
    
    async def get_chat_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get chat history for a user"""
        try:
            result = (
                self.supabase.table("chat_messages")
                .select("sender, message, timestamp")
                .eq("user_id", user_id)
                .order("timestamp", desc=False)
                .limit(limit)
                .execute()
            )
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Get chat history error: {str(e)}")
            return []
    
    async def clear_chat_history(self, user_id: str):
        """Clear chat history for a user"""
        try:
            result = self.supabase.table("chat_messages").delete().eq("user_id", user_id).execute()
            
            if result.data is None:
                raise Exception("Failed to clear chat history")
                
        except Exception as e:
            logger.error(f"Clear chat history error: {str(e)}")
            raise
    
    # Supplement logs operations
    async def create_supplement_log(
        self, 
        user_id: str, 
        supplement_id: int, 
        scheduled_time: str,
        status: str = "pending"
    ) -> Dict[str, Any]:
        """Create a supplement log entry"""
        try:
            log_record = {
                "user_id": user_id,
                "supplement_id": supplement_id,
                "scheduled_time": scheduled_time,
                "status": status,
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = self.supabase.table("supplement_logs").insert(log_record).execute()
            
            if result.data:
                return result.data[0]
            else:
                raise Exception("Failed to create supplement log")
                
        except Exception as e:
            logger.error(f"Create supplement log error: {str(e)}")
            raise
    
    async def update_supplement_log(
        self, 
        log_id: str, 
        status: str, 
        taken_at: Optional[datetime] = None,
        notes: Optional[str] = None
    ):
        """Update supplement log status"""
        try:
            update_data = {"status": status}
            
            if taken_at:
                update_data["taken_at"] = taken_at.isoformat()
            if notes:
                update_data["notes"] = notes
            
            result = self.supabase.table("supplement_logs").update(update_data).eq("id", log_id).execute()
            
            if not result.data:
                raise Exception("Failed to update supplement log")
                
        except Exception as e:
            logger.error(f"Update supplement log error: {str(e)}")
            raise
    
    async def get_supplement_logs(
        self, 
        user_id: str, 
        date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get supplement logs for a user"""
        try:
            query = self.supabase.table("supplement_logs").select("*").eq("user_id", user_id)
            
            if date:
                # Filter by date if provided
                query = query.gte("created_at", f"{date}T00:00:00").lt("created_at", f"{date}T23:59:59")
            
            result = query.order("scheduled_time").execute()
            return result.data or []
            
        except Exception as e:
            logger.error(f"Get supplement logs error: {str(e)}")
            return []

# Dependency for FastAPI
from typing import AsyncGenerator

async def get_database() -> AsyncGenerator[Database, None]:
    """Get database instance for dependency injection"""
    db = Database()
    await db.initialize()
    try:
        yield db
    finally:
        await db.close()