from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from snapshot import collect_snapshot

OBSERVED_AT = datetime(2026, 8, 9, 16, 30, tzinfo=timezone.utc)


def _load_plugin(monkeypatch):
    root = Path(__file__).resolve().parent.parent
    module_name = "protoagent_plugin_operator_control_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    assert spec is not None and spec.loader is not None
    plugin = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, plugin)
    spec.loader.exec_module(plugin)
    return plugin


@pytest.mark.asyncio
async def test_collects_one_target_as_normalized_live_read_only_evidence():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/healthz":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "graph_compiled": True,
                    "setup_complete": True,
                    "ui": "none",
                    "model": "must-not-leak",
                },
            )
        if request.url.path == "/api/runtime/status":
            return httpx.Response(
                200,
                json={
                    "setup_complete": True,
                    "graph_loaded": True,
                    "version": "0.115.0",
                    "instance_uid": "must-not-leak",
                    "plugins": [
                        {"id": "github", "name": "GitHub", "version": "0.4.0", "enabled": True},
                        {"id": "notes", "name": "Notes", "version": "0.2.0", "enabled": False},
                    ],
                    "skills": {"enabled": True, "count": 12, "configured_path": "/private/skills.db"},
                    "mcp": {"enabled": True, "tool_count": 3, "servers": [{"env": {"TOKEN": "must-not-leak"}}]},
                    "warnings": [],
                    "identity": {"operator": "must-not-leak"},
                },
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        snapshot = await collect_snapshot(
            "http://127.0.0.1:8123/",
            token="super-secret",
            client=client,
            observed_at=OBSERVED_AT,
        )

    assert {(request.method, request.url.path) for request in requests} == {
        ("GET", "/healthz"),
        ("GET", "/api/runtime/status"),
    }
    assert all(request.headers["authorization"] == "Bearer super-secret" for request in requests)
    assert snapshot == {
        "schema_version": "operator.snapshot.v1",
        "target": {"base_url": "http://127.0.0.1:8123"},
        "observed_at": "2026-08-09T16:30:00Z",
        "freshness": "live",
        "status": "ready",
        "sources": {
            "health": {
                "source": "GET /healthz",
                "observed_at": "2026-08-09T16:30:00Z",
                "state": "available",
                "http_status": 200,
                "evidence": {
                    "ok": True,
                    "graph_compiled": True,
                    "setup_complete": True,
                    "ui": "none",
                },
            },
            "runtime": {
                "source": "GET /api/runtime/status",
                "observed_at": "2026-08-09T16:30:00Z",
                "state": "available",
                "http_status": 200,
                "evidence": {
                    "setup_complete": True,
                    "graph_loaded": True,
                    "version": "0.115.0",
                    "plugins": [
                        {"id": "github", "name": "GitHub", "version": "0.4.0", "enabled": True},
                        {"id": "notes", "name": "Notes", "version": "0.2.0", "enabled": False},
                    ],
                    "skills": {"enabled": True, "count": 12},
                    "mcp": {"enabled": True, "tool_count": 3},
                    "warning_count": 0,
                },
            },
        },
    }
    rendered = json.dumps(snapshot)
    assert "super-secret" not in rendered
    assert "must-not-leak" not in rendered
    assert "/private/skills.db" not in rendered


@pytest.mark.asyncio
async def test_one_failed_source_is_isolated_and_marks_snapshot_degraded():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(
                200,
                json={"ok": True, "graph_compiled": True, "setup_complete": True, "ui": "none"},
            )
        raise httpx.ConnectError("runtime endpoint unavailable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        snapshot = await collect_snapshot(
            "http://127.0.0.1:8123",
            client=client,
            observed_at=OBSERVED_AT,
        )

    assert snapshot["status"] == "degraded"
    assert snapshot["sources"]["health"]["state"] == "available"
    assert snapshot["sources"]["runtime"] == {
        "source": "GET /api/runtime/status",
        "observed_at": "2026-08-09T16:30:00Z",
        "state": "unavailable",
        "http_status": None,
        "error": "runtime endpoint unavailable",
    }


@pytest.mark.asyncio
async def test_health_503_is_available_negative_evidence_not_a_transport_failure():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(
                503,
                json={"ok": False, "graph_compiled": False, "setup_complete": True, "ui": "none"},
            )
        return httpx.Response(
            200,
            json={
                "setup_complete": True,
                "graph_loaded": False,
                "version": "0.115.0",
                "plugins": [],
                "skills": {},
                "mcp": {},
                "warnings": [],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        snapshot = await collect_snapshot(
            "http://127.0.0.1:8123",
            client=client,
            observed_at=OBSERVED_AT,
        )

    assert snapshot["status"] == "not_ready"
    assert snapshot["sources"]["health"]["state"] == "available"
    assert snapshot["sources"]["health"]["http_status"] == 503
    assert snapshot["sources"]["health"]["evidence"]["ok"] is False


@pytest.mark.asyncio
async def test_rejects_non_http_and_credential_bearing_targets():
    with pytest.raises(ValueError, match="http or https"):
        await collect_snapshot("file:///etc/passwd")
    with pytest.raises(ValueError, match="must not contain credentials"):
        await collect_snapshot("https://user:secret@example.test")


def test_registers_one_read_only_zero_argument_tool(monkeypatch):
    plugin = _load_plugin(monkeypatch)
    registered = []
    registry = SimpleNamespace(
        config={"target_url": "http://127.0.0.1:8123", "token": "secret", "timeout_seconds": 4},
        register_tool=registered.append,
    )

    plugin.register(registry)

    assert [tool.name for tool in registered] == ["operator_snapshot"]
    assert registered[0].args == {}


@pytest.mark.asyncio
async def test_unconfigured_tool_returns_without_network_activity(monkeypatch):
    plugin = _load_plugin(monkeypatch)

    async def unexpected_network(*args, **kwargs):
        raise AssertionError("unconfigured tool attempted network activity")

    monkeypatch.setattr(plugin, "collect_snapshot", unexpected_network)
    tool = plugin._build_tool({})

    result = json.loads(await tool.ainvoke({}))

    assert result == {
        "schema_version": "operator.snapshot.v1",
        "status": "not_configured",
        "error": "Configure operator_control.target_url before inspecting a target.",
    }
