import httpx
from typing import Optional, Dict, Any, List
from ..core.config import settings, LoraConfig


def _normalize_address(address: str) -> str:
    address = (address or "").strip().rstrip("/")
    return address if address.startswith("http") else f"http://{address}"


class SwarmUIClient:
    """SwarmUI HTTP client.

    The address is read from settings.swarmui.address on every call, so a
    Settings change takes effect immediately; a per-request ``address``
    override is one-shot and never stored on the shared client. Sessions
    are kept per address (a session id is only valid on its own server).
    """

    def __init__(self):
        self._sessions: Dict[str, str] = {}

    @property
    def address(self) -> str:
        return _normalize_address(settings.swarmui.address)

    def _base(self, address: Optional[str] = None) -> str:
        return _normalize_address(address) if address else self.address

    @property
    def session_id(self) -> str:
        return self._sessions.get(self.address, "")

    async def get_session(self, address: Optional[str] = None) -> bool:
        """Acquire a session with brief retries (SwarmUI restarts are transient)."""
        import asyncio
        base = self._base(address)
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    response = await client.post(
                        f"{base}/API/GetNewSession",
                        json={}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        self._sessions[base] = data.get("session_id", "")
                        return True
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug("SwarmUI session attempt %d failed: %s", attempt + 1, e)
            if attempt < 2:
                await asyncio.sleep(1.5)
        return False

    async def ensure_session(self, address: Optional[str] = None) -> bool:
        if not self._sessions.get(self._base(address)):
            return await self.get_session(address)
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
        base = self.address
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{base}/API/GetNewSession",
                    json={}
                )
                if response.status_code == 200:
                    data = response.json()
                    self._sessions[base] = data.get("session_id", "")
                    return {"connected": True, "status": "ok", "version": data.get("version", "")}
                return {"connected": False, "status": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"connected": False, "status": str(e)}

    async def get_models(self) -> List[str]:
        base = self.address
        if not await self.ensure_session(base):
            return []
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{base}/API/GenerateText2Image",
                    json={
                        "session_id": self._sessions.get(base, ""),
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
        base = self.address
        if not await self.ensure_session(base):
            return []
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{base}/API/ListModels",
                    json={"session_id": self._sessions.get(base, ""), "path": "", "depth": 3,
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
                    "trigger_phrase": f.get("trigger_phrase") or "",
                } for f in files]
        except Exception:
            return []

    async def ipadapter_features(self, _retry: bool = True) -> Dict[str, Any]:
        """Whether a running backend has SwarmUI's IP-Adapter feature (the
        ComfyUI_IPAdapter_plus node pack) and the "Use IP-Adapter" presets:
        ``{"ipadapter": bool, "presets": [str]}`` ("None" left out)."""
        base = self.address
        out: Dict[str, Any] = {"ipadapter": False, "presets": []}
        if not await self.ensure_session(base):
            return out
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                sid = self._sessions.get(base, "")
                backends = (await client.post(f"{base}/API/ListBackends", json={"session_id": sid})).json()
                if isinstance(backends, dict) and backends.get("error_id") == "invalid_session_id" and _retry:
                    self._sessions.pop(base, None)
                    return await self.ipadapter_features(_retry=False)
                out["ipadapter"] = any("ipadapter" in (b.get("features") or [])
                                       for b in (backends.values() if isinstance(backends, dict) else [])
                                       if isinstance(b, dict) and b.get("status") == "running")
                params = (await client.post(f"{base}/API/ListT2IParams", json={"session_id": sid})).json()
                for p in params.get("list") or []:
                    if p.get("id") == "useipadapter":
                        out["presets"] = [v for v in (p.get("values") or []) if v and v != "None"]
                        break
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("SwarmUI feature probe failed: %s", e)
        if not out["presets"]:
            out["ipadapter"] = False
        return out

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
        address: str = None,             # one-shot server override (not stored)
        prompt_images: List[str] = None, # data URLs: IP-Adapter references (character sheets)
        ipadapter: str = None,           # SwarmUI "Use IP-Adapter" preset, e.g. "PLUS (high strength)"
        ipadapter_weight: float = None,  # 0-1; IP-Adapter strength
        ipadapter_weight_type: str = None,  # "standard" | "prompt is more important" | "style transfer"
        ipadapter_end: float = None,     # 0-1: stop applying it after this fraction of the steps
    ) -> Dict[str, Any]:
        swarmsettings = settings.swarmui
        base = self._base(address)

        if not await self.ensure_session(base):
            return {"success": False, "error": "Failed to get SwarmUI session"}
        
        full_prompt = self.build_prompt_with_loras(prompt, loras or swarmsettings.currentLoras)
        
        payload: Dict[str, Any] = {
            "session_id": self._sessions.get(base, ""),
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
        # IP-Adapter: the reference images ride in "promptimages" (|-joined
        # data URLs) and the preset in "useipadapter" (SwarmUI param ids from
        # /API/ListT2IParams); without a preset the images are not sent, so
        # SwarmUI never falls back to ReVision/unCLIP on them
        refs = [r for r in (prompt_images or []) if r]
        if refs and ipadapter and ipadapter != "None":
            payload["promptimages"] = "|".join(refs)
            payload["useipadapter"] = ipadapter
            if ipadapter_weight is not None:
                payload["ipadapterweight"] = float(ipadapter_weight)
            if ipadapter_weight_type:
                payload["ipadapterweighttype"] = ipadapter_weight_type
            if ipadapter_end is not None:
                payload["ipadapterend"] = float(ipadapter_end)

        import logging
        logger = logging.getLogger(__name__)
        # log everything except embedded images: img2img payloads embed
        # multi-MB base64 data URLs that would bloat the log
        log_payload = {k: (f"<data URL, {len(v)} chars>"
                           if k in ("initimage", "maskimage", "promptimages") else v)
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
                    payload["session_id"] = self._sessions.get(base, "")
                    response = await client.post(
                        f"{base}/API/GenerateText2Image",
                        json=payload
                    )
                    if response.status_code != 200:
                        return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
                    result = response.json()
                    if result.get("error_id") != "invalid_session_id":
                        break
                    self._sessions.pop(base, None)
                    if attempt == 0:
                        if not await self.get_session(base):
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
                            f"{base}/{image_path}"
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
