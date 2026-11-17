"""Per-request LLM configuration is request-local: two concurrent requests
(a batch enhance that awaits each scene, a storyboard on another endpoint
with its own key and model) never send with each other's settings, and the
stored key still only goes to the stored endpoint.

Run: python -m pytest backend/tests/test_llm_request_isolation.py -q
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.core import config, openai_client  # noqa: E402

STORED = "https://stored.example/v1"
OTHER = "https://other.example/v1"


@pytest.fixture
def transport(monkeypatch):
    """httpx.AsyncClient over a MockTransport that records every request and
    yields to the event loop, so concurrent requests interleave."""
    monkeypatch.setattr(config.settings.api, "endpoint", STORED)
    monkeypatch.setattr(config.settings.api, "api_key", "sk-STORED")
    monkeypatch.setattr(config.settings.api, "model", "stored-model")
    sent = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append({"host": request.url.host,
                     "auth": request.headers.get("authorization"),
                     "model": body.get("model")})
        await asyncio.sleep(0.02)
        return httpx.Response(200, json={"choices": [{"message": {
            "content": '[{"id": "panel_1", "scene": "s"}]'}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(openai_client.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler),
                                          **{k: v for k, v in kw.items() if k != "http2"}))
    return sent


def test_concurrent_requests_keep_their_own_settings(transport):
    from backend.api import prompt, storyboard

    async def both():
        batch = prompt.batch_enhance_prompts(prompt.BatchEnhanceRequest(
            scenes=["a", "b", "c"], mode="tags", model="model-a"))
        board = storyboard.generate_storyboard(storyboard.GenerateRequest(
            text="story", endpoint=OTHER, api_key="sk-OTHER", model="model-b"))
        return await asyncio.gather(batch, board)

    batch_result, board_result = asyncio.run(both())
    assert all("error" not in r for r in batch_result["results"]), batch_result
    assert board_result["panels"]
    stored = [s for s in transport if s["host"] == "stored.example"]
    other = [s for s in transport if s["host"] == "other.example"]
    assert len(stored) == 3 and len(other) == 1
    assert all(s == {"host": "stored.example", "auth": "Bearer sk-STORED",
                     "model": "model-a"} for s in stored), stored
    assert other == [{"host": "other.example", "auth": "Bearer sk-OTHER", "model": "model-b"}]


def test_for_request_leaves_the_shared_client_alone(transport):
    shared = openai_client.client
    shared.reload_from_settings()
    llm = shared.for_request(OTHER, None, model="m", temperature=0.2, thinking=False)
    assert (llm.endpoint, llm.api_key, llm.model, llm.temperature, llm.thinking) == \
        (OTHER, "", "m", 0.2, False)          # no stored key for a foreign endpoint
    assert (shared.endpoint, shared.api_key, shared.model) == (STORED, "sk-STORED", "stored-model")
    # the masked echo of the stored key is not a key; the stored one stays
    assert shared.for_request(None, "****ORED").api_key == "sk-STORED"
