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
        """Acquire a session with brief retries (SwarmUI restarts are transient)."""
        import asyncio
        for attempt in range(3):
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
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug("SwarmUI session attempt %d failed: %s", attempt + 1, e)
            if attempt < 2:
                await asyncio.sleep(1.5)
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

    async def list_models(self, subtype: str = "Stable-Diffusion") -> List[Dict[str, Any]]:
        """List installed models with architecture metadata (SwarmUI ListModels)."""
        if not await self.ensure_session():
            return []
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{self.address}/API/ListModels",
                    json={"session_id": self.session_id, "path": "", "depth": 3,
                          "subtype": subtype},
                )
                if response.status_code != 200:
                    return []
                files = response.json().get("files", [])
                return [{
                    "name": f.get("name", ""),
                    "title": f.get("title", ""),
                    "architecture": f.get("architecture", ""),
                    "class": f.get("class", ""),
                    "standard_width": f.get("standard_width", 0),
                    "standard_height": f.get("standard_height", 0),
                } for f in files]
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
        init_image: str = None,          # data URL for img2img
        init_creativity: float = None,   # denoise strength 0-1
        mask_image: str = None,          # data URL inpaint mask (with init_image)
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
        if init_image:
            payload["initimage"] = init_image
            if init_creativity is not None:
                payload["initimagecreativity"] = float(init_creativity)
            if mask_image:
                payload["maskimage"] = mask_image

        import logging
        logger = logging.getLogger(__name__)
        # log everything except embedded images: img2img payloads embed
        # multi-MB base64 data URLs that would bloat the log
        log_payload = {k: (f"<data URL, {len(v)} chars>"
                           if k in ("initimage", "maskimage") else v)
                       for k, v in payload.items()}
        logger.info("[SwarmUI] FULL PAYLOAD: %s", log_payload)

        if sampler_name and sampler_name != swarmsettings.currentSamplerName:
            payload["sampler"] = sampler_name

        try:
            async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
                # One replay on session expiry: the SAME payload (including
                # initimage / removebackground) is re-sent with a fresh
                # session id — never degraded to a plain text2image call.
                result = None
                for attempt in range(2):
                    payload["session_id"] = self.session_id
                    response = await client.post(
                        f"{self.address}/API/GenerateText2Image",
                        json=payload
                    )
                    if response.status_code != 200:
                        return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
                    result = response.json()
                    if result.get("error_id") != "invalid_session_id":
                        break
                    self.session_expired = True
                    if attempt == 0:
                        if not await self.get_session():
                            return {"success": False, "error": "Failed to renew SwarmUI session"}
                        logger.info("[SwarmUI] session expired; replaying payload with new session")
                        continue
                    return {"success": False, "error": "SwarmUI session expired"}

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

        except Exception as e:
            return {"success": False, "error": str(e)}


swarm_client = SwarmUIClient()
