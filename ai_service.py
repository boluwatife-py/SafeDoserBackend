import os
import logging
import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class AIService:
    """AI service for generating medical assistance responses"""

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = None

        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info("Gemini client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                self.client = None
        else:
            logger.warning("No GEMINI_API_KEY provided — using fallback responses")

    async def generate_response(
        self,
        user_message: str,
        context: Dict[str, Any],
        chat_history: List[Dict[str, Any]]
    ) -> str:
        """Generate AI response to user message"""
        try:
            if self.client:
                return await self._generate_gemini_response(user_message, context, chat_history)
            return self._generate_fallback_response(user_message, context)
        except Exception as e:
            logger.error(f"AI response generation error: {e}")
            return self._generate_fallback_response(user_message, context)

    async def _generate_gemini_response(
        self,
        user_message: str,
        context: Dict[str, Any],
        chat_history: List[Dict[str, Any]]
    ) -> str:
        """Generate response using Gemini AI"""
        if self.client is None:
            raise RuntimeError("Gemini client is not initialized")

        prompt = self._build_medical_prompt(user_message, context, chat_history)
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                ),
            )
            return response.text or "I'm sorry, I couldn't generate a helpful response at this time."
        except Exception as e:
            logger.error(f"Gemini AI error: {e}")
            return "I'm sorry, I couldn't generate a helpful response at this time."

    def _build_medical_prompt(
        self,
        user_message: str,
        context: Dict[str, Any],
        chat_history: List[Dict[str, Any]]
    ) -> str:
        """Build a concise medical prompt with context and history"""
        
        # Get user context
        user_name = context.get("user_name", "")
        user_age = context.get("user_age", "")
        supplements = context.get("supplements", [])
        
        # Build supplement context
        supplement_context = ""
        if supplements:
            supplement_list = []
            for supp in supplements:
                name = supp.get('name', 'Unknown')
                form = supp.get('dosage_form', '')
                freq = supp.get('frequency', '')
                supplement_list.append(f"{name} ({form}, {freq})")
            supplement_context = f"Current supplements: {', '.join(supplement_list[:3])}" # Limit to 3 for brevity
            if len(supplements) > 3:
                supplement_context += f" and {len(supplements) - 3} more"
        
        # Build conversation history (last 3 exchanges only)
        history_context = ""
        recent_history = chat_history[-6:] if chat_history else []
        if recent_history:
            history_parts = []
            for msg in recent_history:
                sender = "User" if msg.get('sender') == 'user' else "Assistant"
                text = msg.get('message', '')[:100] # Truncate long messages
                history_parts.append(f"{sender}: {text}")
            history_context = f"Recent conversation: {' | '.join(history_parts)}"

        # Concise system prompt
        system_prompt = f"""You are SafeDoser Assistant, a helpful medical AI for supplement and medication guidance.

GUIDELINES:
- Be concise and helpful (2-3 sentences max for simple questions)
- Only mention user's name/age when directly relevant to the medical advice
- Prioritize safety - recommend healthcare providers for serious concerns
- Provide evidence-based information
- Never diagnose conditions

CONTEXT:
User: {user_name}, {user_age} years old
{supplement_context}
{history_context}

USER QUESTION: {user_message}

Provide a helpful, concise response. Use the user's name sparingly and only when it adds value to the response."""

        return system_prompt

    def _generate_fallback_response(
        self,
        user_message: str,
        context: Dict[str, Any]
    ) -> str:
        """Generate an intelligent fallback response when AI is unavailable"""
        user_name = context.get("user_name", "")
        supplements = context.get("supplements", [])
        lower_message = user_message.lower()

        # Greeting responses
        if any(word in lower_message for word in ['hello', 'hi', 'hey', 'good morning', 'good afternoon']):
            greeting = "Hello! 👋" if not user_name else f"Hello {user_name}! 👋"
            return f"{greeting} I'm here to help with questions about your medications and supplements. What would you like to know? 💊"

        # Supplement-specific questions
        mentioned_supplement = None
        for supp in supplements:
            if supp.get('name', '').lower() in lower_message:
                mentioned_supplement = supp
                break

        if mentioned_supplement:
            name = mentioned_supplement.get('name', 'this supplement')
            return f"I can help with {name}! What specifically would you like to know - timing, interactions, benefits, or side effects? For personalized dosing advice, always consult your healthcare provider. 💊"

        # Drug interaction questions
        if any(word in lower_message for word in ['interaction', 'interact', 'together', 'combine']):
            if not supplements:
                return "You don't have any supplements tracked yet. When you add them, I can help check for potential interactions! 🔍"
            return "I can help with interaction information! Some supplements compete for absorption (like calcium and iron), while others work better together. For prescription drug interactions, always check with your pharmacist. What specific interaction concerns do you have?"

        # Side effects questions
        if any(word in lower_message for word in ['side effect', 'adverse', 'reaction', 'problem']):
            return "Side effects are important to monitor. Common supplement side effects include digestive upset or headaches. If you're experiencing concerning symptoms, contact your healthcare provider immediately. What specific concerns do you have? ⚕️"

        # Dosage questions
        if any(word in lower_message for word in ['dose', 'dosage', 'how much', 'amount']):
            return "Dosage questions are crucial for safety! I recommend confirming all dosages with your healthcare provider or pharmacist. Never adjust doses without medical supervision. What specific dosage question do you have? 📋"

        # Timing questions
        if any(word in lower_message for word in ['when', 'time', 'timing', 'schedule']):
            if not supplements:
                return "You don't have supplements scheduled yet. When you add them, I can help optimize timing for best absorption! ⏰"
            return "Great question about timing! Morning is best for energizing supplements (B vitamins), evening for relaxing ones (magnesium). Fat-soluble vitamins work better with meals. What timing question do you have? ⏰"

        # General health questions
        if any(word in lower_message for word in ['health', 'benefit', 'good for', 'help with']):
            return "Supplements work best as part of a healthy lifestyle with proper diet and exercise. Each supplement has specific benefits - what particular health goal or supplement are you curious about? 🌟"

        # Default response
        return "I can help with supplement information, interactions, timing, dosage guidance, and general health questions. What would you like to know? For personalized medical advice, always consult your healthcare provider."

    def _get_supplement_info(self, name: str, age: int) -> str:
        """Get basic information about a supplement"""
        lower_name = name.lower()
        
        if 'vitamin d' in lower_name:
            return "Vitamin D3 supports bone health and immune function. Best absorbed with fat-containing meals. Consider checking blood levels annually."
        
        if 'omega' in lower_name or 'fish oil' in lower_name:
            return "Omega-3 supports heart and brain health. Take with meals to reduce aftertaste. Look for EPA/DHA content on labels."
        
        if 'magnesium' in lower_name:
            return "Magnesium supports muscle function and sleep. Evening timing is often preferred as it can be relaxing."
        
        if 'vitamin c' in lower_name:
            return "Vitamin C is a powerful antioxidant supporting immune function. Timing is flexible since it's water-soluble."
        
        if 'probiotic' in lower_name:
            return "Probiotics support digestive and immune health. Best taken consistently, often with meals."
        
        if 'melatonin' in lower_name:
            return "Melatonin helps regulate sleep cycles. Take 30-60 minutes before bedtime. Start with the lowest effective dose."
        
        return "This supplement can be beneficial as part of a balanced health regimen. Consult your healthcare provider for specific guidance."

    def _get_basic_interaction_info(self, name: str) -> str:
        """Get basic interaction information for a supplement"""
        lower_name = name.lower()
        
        if 'vitamin d' in lower_name:
            return 'Works well with calcium, avoid with thiazide diuretics'
        if 'omega' in lower_name:
            return 'May enhance blood-thinning medications'
        if 'magnesium' in lower_name:
            return 'Can affect absorption of antibiotics'
        if 'vitamin c' in lower_name:
            return 'Enhances iron absorption'
        if 'probiotic' in lower_name:
            return 'Take 2+ hours apart from antibiotics'
        if 'melatonin' in lower_name:
            return 'May interact with blood thinners'
        
        return 'Check with pharmacist for specific interactions'

    def _get_basic_benefit_info(self, name: str) -> str:
        """Get basic benefit information for a supplement"""
        lower_name = name.lower()
        
        if 'vitamin d' in lower_name:
            return 'Bone health, immune support'
        if 'omega' in lower_name:
            return 'Heart health, brain function'
        if 'magnesium' in lower_name:
            return 'Muscle function, sleep quality'
        if 'vitamin c' in lower_name:
            return 'Immune support, antioxidant protection'
        if 'probiotic' in lower_name:
            return 'Digestive health, immune support'
        if 'melatonin' in lower_name:
            return 'Sleep regulation'
        
        return 'Supports overall health and wellness'