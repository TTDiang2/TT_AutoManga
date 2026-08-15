import httpx
from typing import Optional, Dict, Any, List
from ..core.config import settings, LoraConfig


class SwarmUIClient:
    def __init__(self):
        self.address = settings.swarmui.address
        self.session_id: str = ""
        self.session_expired: bool = True

    def update_address(self, address: str):
        self.address = address if address.startswith("http") else f"http://{address}"

    async def get_session(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{self.address}/API/GetNewSession",
                    json={}
                )
                if response.status_code == 200:
                    data = response.json()
                    self.session_id = data.get("session_id", "")
                    self.session_expired = False
                    return True
                return False
        except Exception:
            return False

    async def ensure_session(self) -> bool:
        if not self.session_id or self.session_expired:
            return await self.get_session()
        return True

    def build_prompt_with_loras(self, prompt: str, loras: List[LoraConfig]) -> str:
        parts = [prompt]
        if loras:
            lora_tags = " ".join(f"<lora:{lora.name}:{lora.weight}>" for lora in loras if lora.name)
            if lora_tags:
                parts.append(lora_tags)
        suffix = settings.swarmui.promptSuffix
        if suffix:
            parts.append(suffix)
        return " ".join(parts)

    async def check_connection(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{self.address}/API/GetNewSession",
                    json={}
                )
                if response.status_code == 200:
                    data = response.json()
                    self.session_id = data.get("session_id", "")
                    return {"connected": True, "status": "ok", "version": data.get("version", "")}
                return {"connected": False, "status": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"connected": False, "status": str(e)}

    async def get_models(self) -> List[str]:
        if not await self.ensure_session():
            return []
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{self.address}/API/GenerateText2Image",
                    json={
                        "session_id": self.session_id,
                        "images": 1,
                        "prompt": "",
                        "model": "",
                        "get_models": True
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if "models" in data:
                        return data["models"]
                    return []
                return []
        except Exception:
            return []

    async def generate_image(
        self, 
        prompt: str, 
        negative_prompt: str = "",
        model: str = None,
        steps: int = None,
        cfg_scale: float = None,
        width: int = None,
        height: int = None,
        sampler_name: str = None,
        loras: List[LoraConfig] = None,
        seed: int = None,
        remove_background: bool = False,
    ) -> Dict[str, Any]:
        swarmsettings = settings.swarmui
        
        if not await self.ensure_session():
            return {"success": False, "error": "Failed to get SwarmUI session"}
        
        full_prompt = self.build_prompt_with_loras(prompt, loras or swarmsettings.currentLoras)
        
        payload: Dict[str, Any] = {
            "session_id": self.session_id,
            "images": 1,
            "prompt": full_prompt,
            "negativeprompt": negative_prompt or "",
            "model": model or swarmsettings.currentModel or "",
            "width": width or swarmsettings.currentWidth or 1024,
            "height": height or swarmsettings.currentHeight or 1024,
            "cfgscale": cfg_scale or swarmsettings.currentCfgScale or 7.0,
            "steps": steps or swarmsettings.currentSteps or 20,
            "seed": seed if seed is not None else -1,
            "donotsave": True,
            "removebackground": remove_background,
        }

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[SwarmUI] FULL PAYLOAD: {payload}")

        if sampler_name and sampler_name != swarmsettings.currentSamplerName:
            payload["sampler"] = sampler_name

        try:
            async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{self.address}/API/GenerateText2Image",
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    if result.get("error_id") == "invalid_session_id":
                        self.session_expired = True
                        return await self.generate_image(
                            prompt, negative_prompt, model, steps, 
                            cfg_scale, width, height, sampler_name, loras, seed
                        )
                    
                    if result.get("error"):
                        return {"success": False, "error": result["error"]}
                    
                    images = result.get("images", [])
                    if images:
                        image_path = images[0]
                        
                        # If image_path is a data URL or extremely long, skip download and return path directly
                        if image_path.startswith('data:') or len(image_path) > 1000:
                            return {
                                "success": True,
                                "image": image_path if image_path.startswith('data:') else f"data:image/png;base64,{image_path}",
                                "path": image_path[:100] + "..." if len(image_path) > 100 else image_path
                            }
                        
                        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as img_client:
                            img_response = await img_client.get(
                                f"{self.address}/{image_path}"
                            )
                            if img_response.status_code == 200:
                                import base64
                                img_base64 = base64.b64encode(img_response.content).decode()
                                return {
                                    "success": True,
                                    "image": f"data:image/png;base64,{img_base64}",
                                    "path": image_path
                                }
                            return {"success": False, "error": f"Failed to download image: {img_response.status_code}"}
                    return {"success": False, "error": "No images in response"}
                else:
                    return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
                    
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        return {"progress": 0, "status": "not_implemented", "message": "Use WebSocket for real-time progress"}


swarm_client = SwarmUIClient()
