"""
Utility functions for SafeDoser backend
"""

import os
import logging
import base64
import uuid
from typing import Optional
from datetime import datetime
import asyncio

from fastapi import UploadFile, HTTPException
from PIL import Image
import io

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('safedoser.log') if os.getenv('ENVIRONMENT') == 'production' else logging.NullHandler()
        ]
    )

async def handle_image_upload(file: UploadFile, user_id: str) -> str:
    """Handle image upload and return URL"""
    try:
        # Read file content
        content = await file.read()
        
        # Validate image
        try:
            image = Image.open(io.BytesIO(content))
            image.verify()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid image file")
        
        # Reset file pointer
        await file.seek(0)
        content = await file.read()
        
        # Resize image if too large
        if len(content) > 5 * 1024 * 1024:  # 5MB limit
            image = Image.open(io.BytesIO(content))
            
            # Calculate new size maintaining aspect ratio
            max_size = (800, 800)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save resized image
            output = io.BytesIO()
            format = image.format or 'JPEG'
            image.save(output, format=format, quality=85)
            content = output.getvalue()
        
        # In a real implementation, you would upload to cloud storage
        # For now, we'll return a base64 data URL
        base64_content = base64.b64encode(content).decode('utf-8')
        mime_type = file.content_type or 'image/jpeg'
        
        return f"data:{mime_type};base64,{base64_content}"
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Image upload error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to upload image")

def generate_unique_filename(original_filename: str) -> str:
    """Generate unique filename for uploads"""
    ext = os.path.splitext(original_filename)[1]
    unique_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return f"{timestamp}_{unique_id}{ext}"

def validate_image_type(content_type: str) -> bool:
    """Validate if content type is a supported image format"""
    allowed_types = [
        'image/jpeg',
        'image/jpg', 
        'image/png',
        'image/gif',
        'image/webp'
    ]
    return content_type.lower() in allowed_types

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage"""
    import re
    # Remove any non-alphanumeric characters except dots and hyphens
    sanitized = re.sub(r'[^a-zA-Z0-9.-]', '_', filename)
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized

async def compress_image(image_data: bytes, max_size: tuple = (800, 800), quality: int = 85) -> bytes:
    """Compress image to reduce file size"""
    try:
        image = Image.open(io.BytesIO(image_data))
        
        # Convert to RGB if necessary
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = background
        
        # Resize if larger than max_size
        if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save compressed image
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=quality, optimize=True)
        
        return output.getvalue()
        
    except Exception as e:
        logging.error(f"Image compression error: {str(e)}")
        return image_data  # Return original if compression fails

def format_supplement_time(time_str: str) -> str:
    """Format supplement time for display"""
    try:
        from datetime import datetime
        time_obj = datetime.strptime(time_str, '%H:%M')
        return time_obj.strftime('%I:%M %p')
    except:
        return time_str

def parse_times_of_day(times_data: dict) -> dict:
    """Parse and validate times of day data"""
    parsed = {
        'Morning': [],
        'Afternoon': [],
        'Evening': []
    }
    
    for period, times in times_data.items():
        if period in parsed and isinstance(times, list):
            for time_str in times:
                if isinstance(time_str, str):
                    try:
                        # Validate time format
                        datetime.strptime(time_str, '%H:%M')
                        parsed[period].append(time_str)
                    except ValueError:
                        continue
    
    return parsed

def calculate_next_dose_time(supplement_data: dict) -> Optional[datetime]:
    """Calculate the next dose time for a supplement"""
    try:
        times_of_day = supplement_data.get('times_of_day', {})
        current_time = datetime.now()
        
        all_times = []
        for period, times in times_of_day.items():
            for time_str in times:
                try:
                    time_obj = datetime.strptime(time_str, '%H:%M').time()
                    next_dose = datetime.combine(current_time.date(), time_obj)
                    
                    # If time has passed today, schedule for tomorrow
                    if next_dose <= current_time:
                        next_dose = next_dose.replace(day=next_dose.day + 1)
                    
                    all_times.append(next_dose)
                except ValueError:
                    continue
        
        return min(all_times) if all_times else None
        
    except Exception:
        return None

def get_supplement_status(supplement_data: dict, current_time: datetime = None) -> str:
    """Get current status of a supplement (due, upcoming, missed)"""
    if current_time is None:
        current_time = datetime.now()
    
    try:
        times_of_day = supplement_data.get('times_of_day', {})
        
        for period, times in times_of_day.items():
            for time_str in times:
                try:
                    time_obj = datetime.strptime(time_str, '%H:%M').time()
                    dose_time = datetime.combine(current_time.date(), time_obj)
                    
                    # Check if dose is due (within 30 minutes)
                    time_diff = (dose_time - current_time).total_seconds() / 60
                    
                    if -30 <= time_diff <= 30:
                        return 'due'
                    elif time_diff < -30:
                        return 'missed'
                    elif time_diff > 30:
                        return 'upcoming'
                        
                except ValueError:
                    continue
        
        return 'scheduled'
        
    except Exception:
        return 'unknown'

class AsyncTimer:
    """Async timer utility for scheduling tasks"""
    
    def __init__(self):
        self.tasks = {}
    
    async def schedule_task(self, task_id: str, delay: float, callback, *args, **kwargs):
        """Schedule a task to run after delay seconds"""
        async def run_task():
            await asyncio.sleep(delay)
            await callback(*args, **kwargs)
            self.tasks.pop(task_id, None)
        
        # Cancel existing task if any
        if task_id in self.tasks:
            self.tasks[task_id].cancel()
        
        # Schedule new task
        self.tasks[task_id] = asyncio.create_task(run_task())
    
    def cancel_task(self, task_id: str):
        """Cancel a scheduled task"""
        if task_id in self.tasks:
            self.tasks[task_id].cancel()
            self.tasks.pop(task_id, None)
    
    def cancel_all_tasks(self):
        """Cancel all scheduled tasks"""
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()

# Global timer instance
timer = AsyncTimer()

def get_timer() -> AsyncTimer:
    """Get global timer instance"""
    return timer