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
            return response.text or "I'm sorry, I couldn’t generate a helpful response at this time."
        except Exception as e:
            logger.error(f"Gemini AI error: {e}")
            return "I'm sorry, I couldn’t generate a helpful response at this time."

    def _build_medical_prompt(
        self,
        user_message: str,
        context: Dict[str, Any],
        chat_history: List[Dict[str, Any]]
    ) -> str:
        """Build a detailed medical prompt with context and history"""
        medical_prompt = """
You are SafeDoser Assistant — a friendly, helpful AI assistant specializing in medications, supplements, and health guidance. 
You have access to comprehensive medical databases and drug interaction information.

💡 IMPORTANT:
• Always put user safety first — recommend seeing a doctor if anything serious comes up.
• Give evidence-based info from trustworthy medical sources.
• Be kind, human, and approachable — speak naturally like you’re chatting with a caring healthcare expert.
• Never diagnose — just provide helpful educational information.
• Always remind them to check with their healthcare provider for personalized advice.
• Consider their age, current supplements, and other personal context they give you.
• Assume the user's name and age are already provided — use them to personalize your responses.

🧠 KNOWLEDGE AREAS:
• Drug interactions and safety
• Benefits, side effects, and proper usage of supplements
• Best timing to take medications and supplements
• Age-specific considerations (e.g. senior or pediatric advice)
• Common health topics and treatments
• How to help users stay on track with their regimen

💬 RESPONSE STYLE:
• Speak like a friendly, knowledgeable person.
• Use a warm, natural tone — not robotic.
• Be clear, concise, and supportive.
• Personalize by using the user's name and acknowledging their age.
• Sprinkle in a few appropriate emojis (💊, ⚕️, 🩺) to make responses feel kind and human.
• Encourage safe habits and double-checking with a healthcare provider as needed.
"""

        user_name = context.get("user_name", "there")
        user_age = context.get("user_age", "unknown")
        supplements = context.get("supplements", [])
        current_time = context.get("current_time", datetime.utcnow().isoformat())

        context_prompt = f"""
USER CONTEXT:
Name: {user_name}
Age: {user_age} years old
Current Time: {current_time}

Current Supplements:
"""
        if supplements:
            for supp in supplements:
                times_of_day = supp.get("times_of_day", {})
                if isinstance(times_of_day, str):
                    try:
                        times_of_day = json.loads(times_of_day)
                    except:
                        times_of_day = {}
                
                interactions = supp.get("interactions", [])
                if isinstance(interactions, str):
                    try:
                        interactions = json.loads(interactions)
                    except:
                        interactions = []
                
                context_prompt += f"- {supp.get('name', 'Unknown')} ({supp.get('dosage_form', 'unknown form')}) - {supp.get('frequency', 'unknown frequency')}\n"
                context_prompt += f"  Brand: {supp.get('brand', 'Unknown')}\n"
                context_prompt += f"  Dose: {supp.get('dose_quantity', 'unknown')} {supp.get('dose_unit', 'units')}\n"
                
                if interactions:
                    context_prompt += f"  Interactions: {', '.join(interactions)}\n"
        else:
            context_prompt += "No supplements currently tracked\n"

        history_prompt = "\nCONVERSATION HISTORY:\n"
        for msg in chat_history[-6:]:
            history_prompt += f"{msg.get('sender', '').upper()}: {msg.get('message', '')}\n"

        full_prompt = f"""
{medical_prompt}

{context_prompt}

{history_prompt}

USER MESSAGE: {user_message}

Please provide a helpful, medically accurate response considering the user's context and supplement regimen. Always prioritize safety and recommend consulting healthcare providers when appropriate.
"""
        return full_prompt

    def _generate_fallback_response(
        self,
        user_message: str,
        context: Dict[str, Any]
    ) -> str:
        """Generate an intelligent fallback response when AI is unavailable"""
        user_name = context.get("user_name", "there")
        user_age = context.get("user_age", 45)
        supplements = context.get("supplements", [])
        lower_message = user_message.lower()

        # Greeting responses
        if any(word in lower_message for word in ['hello', 'hi', 'hey', 'good morning', 'good afternoon']):
            return f"Hello {user_name}! 👋 I'm here to help you with any questions about your medications and supplements. I see you're currently managing {len(supplements)} supplements. How can I assist you today? 💊"

        # Supplement-specific questions
        mentioned_supplement = None
        for supp in supplements:
            if supp.get('name', '').lower() in lower_message:
                mentioned_supplement = supp
                break

        if mentioned_supplement:
            return self._generate_supplement_specific_response(mentioned_supplement, user_message, user_name, user_age)

        # Drug interaction questions
        if any(word in lower_message for word in ['interaction', 'interact', 'together', 'combine']):
            return self._generate_interaction_response(supplements, user_name)

        # Side effects questions
        if any(word in lower_message for word in ['side effect', 'adverse', 'reaction', 'problem']):
            return f"Side effects are an important consideration, {user_name}. At {user_age} years old, it's especially important to monitor for any unusual symptoms. Common supplement side effects can include digestive upset, headaches, or allergic reactions.\n\nFor your current supplements, I recommend:\n• Monitor for any unusual symptoms\n• Take supplements as directed\n• Report any concerns to your healthcare provider\n\nIf you're experiencing any concerning symptoms, please contact your healthcare provider immediately. Would you like information about any specific supplement? ⚕️"

        # Dosage questions
        if any(word in lower_message for word in ['dose', 'dosage', 'how much', 'amount']):
            return f"Dosage questions are crucial for safety, {user_name}! At {user_age}, proper dosing is especially important. I can see your current supplement schedule, but I always recommend confirming dosages with your healthcare provider or pharmacist.\n\nNever adjust doses without medical supervision. If you're unsure about any dosage, please consult your doctor. Would you like me to review your current supplement timing? 📋"

        # Timing questions
        if any(word in lower_message for word in ['when', 'time', 'timing', 'schedule']):
            return self._generate_timing_response(supplements, user_name)

        # Age-related questions
        if any(word in lower_message for word in ['age', 'older', 'senior', 'elderly']):
            return f"At {user_age} years old, there are some important considerations for supplement use:\n\n🔹 **Absorption**: Some supplements may be absorbed differently with age\n🔹 **Kidney Function**: Important to monitor with certain supplements\n🔹 **Drug Interactions**: More likely if taking multiple medications\n🔹 **Bone Health**: Calcium, Vitamin D, and Magnesium become increasingly important\n\nYour current supplement regimen looks well-balanced. Always discuss any changes with your healthcare provider, especially considering age-related factors. Is there a specific concern you'd like to discuss? 👨‍⚕️"

        # General health questions
        if any(word in lower_message for word in ['health', 'benefit', 'good for', 'help with']):
            return f"Great question about health benefits, {user_name}! Your current supplement regimen shows good attention to overall wellness. Here's what I can tell you about general benefits:\n\n{self._generate_health_benefits_info(supplements)}\n\nRemember, supplements work best as part of a healthy lifestyle including proper diet, exercise, and regular medical check-ups. At {user_age}, maintaining these habits is especially beneficial! 🌟\n\nIs there a specific health goal you're working towards?"

        # Default response with context
        return f"I'd be happy to help you with that, {user_name}! I have access to comprehensive medical information and can see you're currently managing {len(supplements)} supplements.\n\nI can help you with:\n💊 Supplement information and interactions\n⏰ Timing and dosage guidance\n🩺 General health questions\n⚠️ Side effect information\n🔄 Medication adherence tips\n\nCould you be more specific about what you'd like to know? I'm here to provide evidence-based information while always recommending you consult with your healthcare provider for personalized advice."

    def _generate_supplement_specific_response(
        self,
        supplement: Dict[str, Any],
        user_message: str,
        user_name: str,
        user_age: int
    ) -> str:
        """Generate response specific to a mentioned supplement"""
        supplement_name = supplement.get('name', 'Unknown supplement')
        dosage_form = supplement.get('dosage_form', 'unknown form')
        frequency = supplement.get('frequency', 'unknown frequency')
        
        return f"I can help you with information about {supplement_name}, {user_name}!\n\n**Your Current Details:**\n• Form: {dosage_form}\n• Frequency: {frequency}\n• Dose: {supplement.get('dose_quantity', 'unknown')} {supplement.get('dose_unit', 'units')}\n\n{self._get_supplement_info(supplement_name, user_age)}\n\nIs there something specific about {supplement_name} you'd like to know more about? I can discuss timing, interactions, benefits, or any concerns you might have. 💊"

    def _generate_interaction_response(
        self,
        supplements: List[Dict[str, Any]],
        user_name: str
    ) -> str:
        """Generate response about supplement interactions"""
        if not supplements:
            return f"{user_name}, you don't currently have any supplements tracked, so there are no interactions to check. When you add supplements, I can help you identify potential interactions! 🔍"
        
        supplement_names = [s.get('name', 'Unknown') for s in supplements]
        
        return f"Great question about interactions, {user_name}! I can see you're taking: {', '.join(supplement_names)}.\n\n**General Interaction Guidelines:**\n🔹 **Timing**: Some supplements compete for absorption (like calcium and iron)\n🔹 **Food**: Some work better with food, others on empty stomach\n🔹 **Medications**: Always check with your pharmacist about prescription drug interactions\n\n**Your Current Supplements:**\n{self._generate_interaction_info(supplements)}\n\nFor specific interaction concerns, especially with prescription medications, please consult your pharmacist or healthcare provider. They can access comprehensive interaction databases! ⚕️\n\nDo you have a specific interaction concern?"

    def _generate_timing_response(
        self,
        supplements: List[Dict[str, Any]],
        user_name: str
    ) -> str:
        """Generate response about supplement timing"""
        if not supplements:
            return f"{user_name}, you don't have any supplements scheduled yet. When you add them, I can help optimize your timing for best absorption and effectiveness! ⏰"
        
        schedule_info = []
        for supp in supplements:
            name = supp.get('name', 'Unknown')
            frequency = supp.get('frequency', 'unknown frequency')
            schedule_info.append(f"• {name} - {frequency}")
        
        return f"Here's your current supplement schedule, {user_name}:\n\n{chr(10).join(schedule_info)}\n\n**Timing Tips:**\n🌅 **Morning**: Best for energizing supplements (B vitamins, iron)\n🌆 **Evening**: Good for relaxing supplements (magnesium, melatonin)\n🍽️ **With Food**: Fat-soluble vitamins (A, D, E, K) absorb better with meals\n🥛 **Empty Stomach**: Some minerals absorb better without food\n\nYour timing looks well-distributed! Any specific timing concerns or questions about optimal absorption? ⏰"

    def _generate_health_benefits_info(self, supplements: List[Dict]) -> str:
        """Generate health benefits information for supplements"""
        if not supplements:
            return "When you add supplements, I can provide specific benefit information for each one."
        
        benefits = []
        for supp in supplements:
            name = supp.get('name', 'Unknown')
            benefit = self._get_basic_benefit_info(name)
            benefits.append(f"• **{name}**: {benefit}")
        
        return '\n'.join(benefits)

    def _generate_interaction_info(self, supplements: List[Dict]) -> str:
        """Generate interaction information for supplements"""
        interactions = []
        for supp in supplements:
            name = supp.get('name', 'Unknown')
            interaction = self._get_basic_interaction_info(name)
            interactions.append(f"• {name} - {interaction}")
        
        return '\n'.join(interactions)

    def _get_supplement_info(self, name: str, age: int) -> str:
        """Get basic information about a supplement"""
        lower_name = name.lower()
        
        if 'vitamin d' in lower_name:
            return f"**Vitamin D3** is excellent for bone health, especially important at {age}! Best absorbed with fat-containing meals. Supports immune function and calcium absorption. Recommended to check blood levels annually."
        
        if 'omega' in lower_name or 'fish oil' in lower_name:
            return f"**Omega-3** supports heart and brain health - very beneficial at your age! Take with meals to reduce fishy aftertaste. Look for EPA/DHA content on labels. Great for inflammation reduction."
        
        if 'magnesium' in lower_name:
            return "**Magnesium** supports muscle function, sleep, and bone health. Evening timing is often preferred as it can be relaxing. Important for heart rhythm and blood pressure regulation."
        
        if 'vitamin c' in lower_name:
            return "**Vitamin C** is a powerful antioxidant supporting immune function. Water-soluble, so timing is flexible. Helps with iron absorption when taken together."
        
        if 'probiotic' in lower_name:
            return "**Probiotics** support digestive and immune health. Best taken consistently, often with or after meals. Look for multiple strains and adequate CFU count."
        
        if 'melatonin' in lower_name:
            return "**Melatonin** helps regulate sleep cycles. Take 30-60 minutes before desired bedtime. Start with lowest effective dose. Avoid bright lights after taking."
        
        return "This supplement can be beneficial as part of a balanced health regimen. For specific information about benefits, dosing, and interactions, I recommend consulting with your healthcare provider or pharmacist."

    def _get_basic_interaction_info(self, name: str) -> str:
        """Get basic interaction information for a supplement"""
        lower_name = name.lower()
        
        if 'vitamin d' in lower_name:
            return 'Take with calcium for synergy, avoid with thiazide diuretics'
        if 'omega' in lower_name:
            return 'May enhance blood-thinning medications'
        if 'magnesium' in lower_name:
            return 'Can affect absorption of antibiotics and bisphosphonates'
        if 'vitamin c' in lower_name:
            return 'Enhances iron absorption, may affect some medications'
        if 'probiotic' in lower_name:
            return 'Take 2+ hours apart from antibiotics'
        if 'melatonin' in lower_name:
            return 'May interact with blood thinners and diabetes medications'
        
        return 'Check with pharmacist for specific interactions'

    def _get_basic_benefit_info(self, name: str) -> str:
        """Get basic benefit information for a supplement"""
        lower_name = name.lower()
        
        if 'vitamin d' in lower_name:
            return 'Bone health, immune support, calcium absorption'
        if 'omega' in lower_name:
            return 'Heart health, brain function, inflammation reduction'
        if 'magnesium' in lower_name:
            return 'Muscle function, sleep quality, bone health'
        if 'vitamin c' in lower_name:
            return 'Immune support, antioxidant protection, collagen synthesis'
        if 'probiotic' in lower_name:
            return 'Digestive health, immune support, gut microbiome balance'
        if 'melatonin' in lower_name:
            return 'Sleep regulation, circadian rhythm support'
        
        return 'Supports overall health and wellness as part of balanced nutrition'