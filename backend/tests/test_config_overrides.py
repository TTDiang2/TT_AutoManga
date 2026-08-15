"""Regression tests for the two leftover config bugs:

- Bug: per-request endpoint/model overrides were silently discarded because
  OpenAIClient.generate_storyboard / enhance_prompt called
  reload_from_settings() at the start, wiping whatever update_config() the
  API layer had just applied.
- Bug: enhance_prompt used the same system prompt for both "turbo" and
  "tags" modes, so the tags mode never got a tags-focused system prompt.

Run with:
    pip install pytest pytest-asyncio httpx
    python -m pytest backend/tests/test_config_overrides.py -v
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend.core import openai_client  # noqa: E402


@pytest.fixture
def fake_llm():
    """Patch httpx.AsyncClient so chat_completion returns a canned 200."""
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

    patcher = patch("backend.core.openai_client.httpx.AsyncClient",
                    return_value=cm)
    patcher.start()
    yield
    patcher.stop()


# ---------- Bug 1: per-request overrides must survive the call ----------

def test_generate_storyboard_keeps_update_config_overrides(fake_llm):
    """update_config(endpoint=...) set by the API layer must NOT be wiped
    by generate_storyboard. Before the fix the method called
    reload_from_settings() first, resetting endpoint to settings.json."""
    oc = openai_client.OpenAIClient()
    # Simulate what /api/storyboard/generate does before calling.
    oc.reload_from_settings()
    oc.update_config(endpoint="http://override:1234/v1", model="override-model")

    asyncio.run(oc.generate_storyboard("some novel text", 3))

    assert oc.endpoint == "http://override:1234/v1", (
        "generate_storyboard wiped the per-request endpoint override: "
        "%r" % oc.endpoint
    )
    assert oc.model == "override-model", (
        "generate_storyboard wiped the per-request model override: %r"
        % oc.model
    )


def test_enhance_prompt_keeps_update_config_overrides(fake_llm):
    """Same for enhance_prompt: a per-request endpoint override must survive."""
    oc = openai_client.OpenAIClient()
    oc.reload_from_settings()
    oc.update_config(endpoint="http://override:1234/v1", model="override-model")

    asyncio.run(oc.enhance_prompt("a scene", "turbo"))

    assert oc.endpoint == "http://override:1234/v1"
    assert oc.model == "override-model"


# ---------- Bug 2: mode-specific system prompts ----------

def test_enhance_prompt_uses_tags_system_prompt_for_tags_mode(fake_llm):
    """mode='tags' must use tags_system_prompt, not the turbo one."""
    oc = openai_client.OpenAIClient()
    captured = {}

    original = openai_client.OpenAIClient.chat_completion

    async def spy(self, messages, temperature=None, system_prompt=None):
        captured["system_prompt"] = system_prompt
        return await original(self, messages, temperature=temperature,
                              system_prompt=system_prompt)

    with patch.object(openai_client.OpenAIClient, "chat_completion", spy):
        asyncio.run(oc.enhance_prompt("a scene", "tags"))

    assert captured["system_prompt"] == oc.tags_system_prompt, (
        "tags mode should use tags_system_prompt, got %r"
        % captured.get("system_prompt")
    )
    assert captured["system_prompt"] != oc.prompt_system_prompt


def test_enhance_prompt_uses_prompt_system_prompt_for_turbo_mode(fake_llm):
    """mode='turbo' must use prompt_system_prompt."""
    oc = openai_client.OpenAIClient()
    captured = {}

    original = openai_client.OpenAIClient.chat_completion

    async def spy(self, messages, temperature=None, system_prompt=None):
        captured["system_prompt"] = system_prompt
        return await original(self, messages, temperature=temperature,
                              system_prompt=system_prompt)

    with patch.object(openai_client.OpenAIClient, "chat_completion", spy):
        asyncio.run(oc.enhance_prompt("a scene", "turbo"))

    assert captured["system_prompt"] == oc.prompt_system_prompt
    assert captured["system_prompt"] != oc.tags_system_prompt
