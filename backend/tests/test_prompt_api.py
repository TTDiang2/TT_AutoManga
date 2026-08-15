"""Tests for /api/prompt route and OpenAIClient observability.

These tests target the three bugs reported for Prompt Lab:
- Bug #2: prompt route and OpenAIClient emit zero logs. When LLM fails or
  succeeds, nothing is recorded, making incidents invisible.

Run with:
    pip install pytest pytest-asyncio httpx
    cd backend && python -m pytest tests/ -v
"""
import asyncio
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Make `backend` importable when running pytest from repo root.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------- Bug #2 (a): route must emit a log line on every request ----------

def test_enhance_logs_incoming_request(caplog):
    """Every /api/prompt/enhance call must log an INFO line. Today it logs
    nothing, so the user has no idea whether the request reached the backend."""
    caplog.set_level(logging.INFO, logger="backend.api.prompt")
    tc = TestClient(app)
    with patch(
        "backend.core.openai_client.OpenAIClient.enhance_prompt",
        new=AsyncMock(return_value={"enhanced_prompt": "ok", "mode": "turbo"}),
    ):
        r = tc.post(
            "/api/prompt/enhance",
            json={
                "scene_description": "hi",
                "mode": "turbo",
                "endpoint": "http://x",
                "api_key": "",
                "model": "m",
            },
        )
    assert r.status_code == 200, r.text
    # Today this fails: prompt.py logs nothing. After the fix it must pass.
    info_lines = [rec.message for rec in caplog.records if rec.levelno >= logging.INFO]
    assert any("enhance" in m.lower() or "prompt" in m.lower() for m in info_lines), (
        "prompt route logged no INFO line; cannot tell if request reached "
        "the backend. Records seen: %r" % info_lines
    )


def test_enhance_logs_when_llm_fails(caplog):
    """When the LLM call raises, the route must log the failure with enough
    context to diagnose. Today it just raises HTTPException(500) and the
    server log is silent unless the user enables uvicorn logging manually."""
    caplog.set_level(logging.ERROR, logger="backend.api.prompt")
    tc = TestClient(app)
    with patch(
        "backend.core.openai_client.OpenAIClient.enhance_prompt",
        new=AsyncMock(side_effect=RuntimeError("API Error 401: bad key")),
    ):
        r = tc.post(
            "/api/prompt/enhance",
            json={
                "scene_description": "hi",
                "mode": "turbo",
                "endpoint": "http://x",
                "api_key": "",
                "model": "m",
            },
        )
    assert r.status_code == 500
    body = r.json()
    error_records = [rec for rec in caplog.records if rec.levelno >= logging.ERROR]
    assert any("401" in rec.getMessage() or "api error" in rec.getMessage().lower()
               for rec in error_records), (
        "Expected an ERROR log with '401' / 'api error' context. "
        "Got: %r" % [rec.getMessage() for rec in error_records]
    )


# ---------- Bug #2 (b): openai_client must log its own I/O ----------

def test_openai_client_chat_completion_logs_url_and_status(caplog):
    """The httpx call in OpenAIClient.chat_completion has zero observability.
    After the fix it must log the URL it called and the status it got back.
    """
    from backend.core import openai_client

    caplog.set_level(logging.INFO, logger="backend.core.openai_client")
    oc = openai_client.OpenAIClient()
    oc.endpoint = "http://127.0.0.1:9"  # anything — we mock httpx
    oc.api_key = ""
    oc.max_tokens = 100
    oc.model = "m"

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "choices": [{"message": {"content": "ok"}}]
    }
    fake_response.text = '{"choices": [{"message": {"content": "ok"}}]}'

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(
        return_value=MagicMock(post=AsyncMock(return_value=fake_response))
    )
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.core.openai_client.httpx.AsyncClient", return_value=cm):
        asyncio.run(oc.chat_completion([{"role": "user", "content": "hi"}]))

    info_messages = [rec.getMessage() for rec in caplog.records
                     if rec.levelno >= logging.INFO]
    assert any("/chat/completions" in m for m in info_messages), (
        "Expected an INFO log naming the /chat/completions URL. "
        "Got: %r" % info_messages
    )
    assert any("200" in m for m in info_messages), (
        "Expected an INFO log showing the response status. "
        "Got: %r" % info_messages
    )