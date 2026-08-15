import httpx
import logging
from typing import Optional, Dict, Any
from ..core.config import settings

logger = logging.getLogger(__name__)


class OpenAIClient:
    def __init__(self):
        self.reload_from_settings()

    def reload_from_settings(self):
        self.endpoint = settings.api.endpoint
        self.api_key = settings.api.api_key
        self.model = settings.api.model
        self.temperature = settings.api.temperature
        self.max_tokens = settings.api.max_tokens
        self.thinking = settings.api.thinking
        self.storyboard_system_prompt = settings.api.storyboard_system_prompt
        self.prompt_system_prompt = settings.api.prompt_system_prompt
        self.tags_system_prompt = settings.api.tags_system_prompt

    def update_config(self, endpoint: str = None, api_key: str = None, 
                     model: str = None, temperature: float = None, 
                     max_tokens: int = None, thinking: bool = None):
        if endpoint:
            self.endpoint = endpoint
        if api_key is not None:
            self.api_key = api_key
        if model:
            self.model = model
        if temperature is not None:
            self.temperature = temperature
        if max_tokens:
            self.max_tokens = max_tokens
        if thinking is not None:
            self.thinking = thinking

    async def chat_completion(self, messages: list, temperature: float = None, system_prompt: str = None) -> Dict[str, Any]:
        temp = temperature if temperature is not None else self.temperature
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)
        
        payload: Dict[str, Any] = {
            "messages": all_messages,
        }
        
        if temp and temp > 0:
            payload["temperature"] = temp
        
        if self.max_tokens and self.max_tokens > 0:
            payload["max_tokens"] = min(self.max_tokens, 8192)
        
        if self.model:
            payload["model"] = self.model
        
        url = f"{self.endpoint}/chat/completions"
        logger.info(
            "openai.chat_completion url=%s model=%s msgs=%d max_tokens=%d",
            url,
            self.model or "<none>",
            len(all_messages),
            payload.get("max_tokens", 0),
        )
        
        try:
            async with httpx.AsyncClient(timeout=300.0, trust_env=False, http2=False) as http_client:
                response = await http_client.post(
                    url,
                    headers=headers,
                    json=payload
                )
        except httpx.HTTPError as e:
            logger.exception("openai.chat_completion transport error url=%s: %s", url, e)
            raise
        
        logger.info(
            "openai.chat_completion response status=%d url=%s",
            response.status_code,
            url,
        )
        
        if response.status_code != 200:
            error_text = response.text[:500] if response.text else ""
            logger.error(
                "openai.chat_completion non-200 status=%d body=%s",
                response.status_code,
                error_text,
            )
            raise Exception(f"API Error {response.status_code}: {error_text}")
        
        return response.json()

    async def generate_storyboard(self, text: str, detail_level: int) -> Dict[str, Any]:
        detail_prompts = {
            1: "Provide a very abstract summary with only 1-2 key scenes.",
            2: "Provide a brief summary with 3-4 main scenes.",
            3: "Provide a balanced breakdown with 5-6 key scenes.",
            4: "Provide a detailed breakdown with 7-8 scenes including character interactions.",
            5: "Provide a highly detailed breakdown with 10+ scenes, including specific actions, emotions, and dialogues."
        }
        
        prompt = f"""{detail_prompts.get(detail_level, detail_prompts[3])}

Return ONLY a JSON array with this exact structure (no other text):
[
  {{"id": "panel_1", "scene": "scene description", "characters": ["char1", "char2"], "dialogue": "optional dialogue"}},
  ...
]

Novel text:
{text}
"""
        
        messages = [{"role": "user", "content": prompt}]
        
        try:
            result = await self.chat_completion(messages, system_prompt=self.storyboard_system_prompt)
            
            content = result["choices"][0]["message"]["content"]
            import json
            import re
            
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                panels = json.loads(json_match.group())
            else:
                panels = []
            
            return {"panels": panels}
        except Exception as e:
            return {"panels": [], "error": str(e)}

    async def enhance_prompt(self, scene_description: str, mode: str) -> Dict[str, Any]:
        if mode == "turbo":
            system = self.prompt_system_prompt
            prompt_text = f"""Enhance this scene description for AI image generation. Make it more vivid and detailed while maintaining the core elements.

Scene: {scene_description}

Return ONLY the enhanced prompt (no other text):"""
        else:
            system = self.tags_system_prompt
            prompt_text = f"""Convert this scene description into comma-separated SDXL tags with quality and style modifiers. Include (1.0) weight for important elements.

Scene: {scene_description}

Return ONLY the tags (no other text):"""
        
        messages = [{"role": "user", "content": prompt_text}]
        
        try:
            result = await self.chat_completion(messages, temperature=0.8, system_prompt=system)
            
            enhanced = result["choices"][0]["message"]["content"].strip()
            
            return {"enhanced_prompt": enhanced, "mode": mode}
        except Exception as e:
            return {"enhanced_prompt": "", "error": str(e), "mode": mode}


client = OpenAIClient()
