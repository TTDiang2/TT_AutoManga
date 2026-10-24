"""Unit tests for the MCP tool layer (backend/mcp_tools.py) using an
injected httpx.MockTransport — no MCP SDK and no live backend needed."""
import sys
from pathlib import Path

import httpx
import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT.parent))

from backend import mcp_tools  # noqa: E402


PNG_FAKE = b"\x89PNG-fake"


@pytest.fixture()
def transport(monkeypatch):
    """Record requests; answer from a canned routing table."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path,
                      request.read()[:200] if request.content else b""))
        png_route = "/api/agent/projects/p1/pages/pg1/preview.png"
        if request.method == "GET" and request.url.path == png_route:
            return httpx.Response(200, content=PNG_FAKE)
        table = {
            ("GET", "/api/health"): {"status": "ok"},
            ("POST", "/api/agent/projects"): {"project": {"id": "p1"}},
            ("PUT", "/api/agent/projects/p1/panels"): {"panels": []},
            ("GET", "/api/agent/p1"): {},
            ("GET", "/api/agent/templates"): {"templates": [{"id": "manga-4"}]},
            ("POST", "/api/agent/export"): {"pdf": {"path": "x.pdf"}},
            ("POST", "/api/agent/generate"): {"assets": [{"asset_id": "a1"}]},
            ("POST", "/api/agent/projects/p1/pages"): {"page": {"id": "pg1"}},
        }
        key = (request.method, request.url.path)
        if key in table:
            return httpx.Response(200, json=table[key])
        if (request.method, request.url.path) == ("GET", "/preview.png"):
            return httpx.Response(200, content=b"\x89PNG-fake")
        if key == ("GET", "/api/agent/projects/missing"):
            return httpx.Response(404, json={"detail": "Project not found"})
        return httpx.Response(404, json={"detail": f"no route {key}"})

    monkeypatch.setattr(mcp_tools, "_TRANSPORT",
                        httpx.MockTransport(handler))
    return calls


@pytest.mark.asyncio
async def test_health_and_project_flow(transport):
    assert await mcp_tools.health() == {"status": "ok"}
    out = await mcp_tools.create_project("demo")
    assert out["project"]["id"] == "p1"
    assert ("POST", "/api/agent/projects") in [(m, p) for m, p, _ in transport]


@pytest.mark.asyncio
async def test_put_panels_body(transport):
    await mcp_tools.put_panels("p1", [{"scene": "rooftop"}])
    body = transport[-1][2].decode()
    assert '"scene": "rooftop"' in body or '"scene":"rooftop"' in body


@pytest.mark.asyncio
async def test_generate_image_omits_none_fields(transport):
    await mcp_tools.generate_image("1girl, rooftop", seed=7, model="qwen")
    body = transport[-1][2].decode()
    assert "qwen" in body and '"seed":7' in body.replace(" ", "")
    for absent in ("init_image", "panel_id", "width"):
        assert f'"{absent}"' not in body, absent


@pytest.mark.asyncio
async def test_preview_returns_raw_png(transport):
    data = await mcp_tools.render_preview("p1", "pg1")
    assert data == b"\x89PNG-fake"


@pytest.mark.asyncio
async def test_error_maps_to_tool_error(transport):
    with pytest.raises(mcp_tools.ToolError) as e:
        await mcp_tools.get_project("missing")
    assert "404" in str(e.value) and "Project not found" in str(e.value)


@pytest.mark.asyncio
async def test_build_page_rows_template(transport):
    await mcp_tools.build_page("p1", panel_ids=["panel_1"], rows=[2, 3])
    body = transport[-1][2].decode().replace(" ", "")
    assert '"kind":"rows"' in body
    assert "[2,3]" in body
