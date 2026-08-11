from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import snapshot as snapshot_module
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
async def test_collects_configured_fleet_as_deterministic_secret_free_summary():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        host = request.url.host
        if host == "lost.test":
            raise httpx.ConnectError("target unavailable", request=request)
        if request.url.path == "/healthz":
            ready = host == "alpha.test"
            return httpx.Response(
                200 if ready else 503,
                json={
                    "ok": ready,
                    "graph_compiled": ready,
                    "setup_complete": True,
                    "ui": "none",
                    "secret": f"must-not-leak-{host}",
                },
            )
        return httpx.Response(
            200,
            json={
                "setup_complete": True,
                "graph_loaded": host == "alpha.test",
                "version": "0.127.0",
                "plugins": [],
                "skills": {},
                "mcp": {},
                "warnings": [],
            },
        )

    targets = [
        {"id": "zeta", "target_url": "https://zeta.test/", "token": "zeta-secret"},
        {"id": "alpha", "target_url": "https://alpha.test", "token": "alpha-secret"},
        {"id": "lost", "target_url": "https://lost.test", "token": "lost-secret"},
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fleet = await snapshot_module.collect_fleet_snapshot(targets, client=client, observed_at=OBSERVED_AT)

    assert fleet["schema_version"] == "operator.fleet_snapshot.v1"
    assert fleet["observed_at"] == "2026-08-09T16:30:00Z"
    assert fleet["freshness"] == "live"
    assert fleet["status"] == "attention_required"
    assert fleet["summary"] == {
        "total": 3,
        "ready": 1,
        "not_ready": 1,
        "degraded": 0,
        "unreachable": 1,
    }
    assert fleet["findings"] == [
        {
            "code": "target_readiness_attention",
            "severity": "attention",
            "scope": "target",
            "target": "lost",
            "observed_at": "2026-08-09T16:30:00Z",
            "source": "GET /healthz and GET /api/runtime/status",
            "classification": "diagnostic",
            "evidence": {"status": "unreachable"},
            "safe_next_inspection": "Inspect target reachability and authentication before retrying the snapshot.",
        },
        {
            "code": "target_readiness_attention",
            "severity": "attention",
            "scope": "target",
            "target": "zeta",
            "observed_at": "2026-08-09T16:30:00Z",
            "source": "GET /healthz and GET /api/runtime/status",
            "classification": "diagnostic",
            "evidence": {"status": "not_ready"},
            "safe_next_inspection": "Inspect target startup and readiness evidence without changing the target.",
        },
    ]
    assert [target["target"]["id"] for target in fleet["targets"]] == ["alpha", "lost", "zeta"]
    assert [target["status"] for target in fleet["targets"]] == ["ready", "unreachable", "not_ready"]
    assert len(requests) == 6
    assert all(request.method == "GET" for request in requests)
    expected_tokens = {
        "alpha.test": "Bearer alpha-secret",
        "lost.test": "Bearer lost-secret",
        "zeta.test": "Bearer zeta-secret",
    }
    assert all(request.headers["authorization"] == expected_tokens[request.url.host] for request in requests)
    rendered = json.dumps(fleet)
    assert "alpha-secret" not in rendered
    assert "lost-secret" not in rendered
    assert "zeta-secret" not in rendered
    assert "must-not-leak" not in rendered


@pytest.mark.asyncio
async def test_reports_deterministic_source_attributed_fleet_version_skew():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(
                200,
                json={"ok": True, "graph_compiled": True, "setup_complete": True, "ui": "none"},
            )
        versions = {
            "zeta.test": "0.127.0",
            "alpha.test": "0.127.0",
            "beta.test": "0.126.0",
        }
        return httpx.Response(
            200,
            json={
                "setup_complete": True,
                "graph_loaded": True,
                "version": versions[request.url.host],
                "plugins": [],
                "skills": {},
                "mcp": {},
                "warnings": [],
            },
        )

    targets = [
        {"id": "zeta", "target_url": "https://zeta.test"},
        {"id": "beta", "target_url": "https://beta.test"},
        {"id": "alpha", "target_url": "https://alpha.test"},
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fleet = await snapshot_module.collect_fleet_snapshot(targets, client=client, observed_at=OBSERVED_AT)

    assert fleet["status"] == "attention_required"
    assert fleet["findings"] == [
        {
            "code": "fleet_version_skew",
            "severity": "attention",
            "scope": "fleet",
            "observed_at": "2026-08-09T16:30:00Z",
            "source": "GET /api/runtime/status",
            "classification": "signal",
            "evidence": {
                "versions": [
                    {"version": "0.126.0", "targets": ["beta"]},
                    {"version": "0.127.0", "targets": ["alpha", "zeta"]},
                ]
            },
            "safe_next_inspection": "Confirm the intended protoAgent version for each target before considering an update.",
        }
    ]


@pytest.mark.asyncio
async def test_reports_target_attributed_incomplete_plugin_evidence_without_config_details():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(
                200,
                json={"ok": True, "graph_compiled": True, "setup_complete": True, "ui": "none"},
            )
        plugins = []
        if request.url.host == "alpha.test":
            plugins = [
                {
                    "id": "notes",
                    "name": "Notes",
                    "version": "0.2.0",
                    "enabled": True,
                    "incomplete": True,
                    "needs_config": [{"key": "PRIVATE_PATH", "label": "Private path"}],
                },
                {
                    "id": "github",
                    "name": "GitHub",
                    "version": "0.4.0",
                    "enabled": True,
                    "incomplete": True,
                    "needs_config": [{"key": "API_KEY", "label": "API key"}],
                },
                {
                    "id": "disabled",
                    "name": "Disabled",
                    "version": "0.1.0",
                    "enabled": False,
                    "incomplete": True,
                },
                {
                    "id": "ready",
                    "name": "Ready",
                    "version": "1.0.0",
                    "enabled": True,
                    "incomplete": False,
                },
            ]
        return httpx.Response(
            200,
            json={
                "setup_complete": True,
                "graph_loaded": True,
                "version": "0.127.0",
                "plugins": plugins,
                "skills": {},
                "mcp": {},
                "warnings": [],
            },
        )

    targets = [
        {"id": "beta", "target_url": "https://beta.test"},
        {"id": "alpha", "target_url": "https://alpha.test"},
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fleet = await snapshot_module.collect_fleet_snapshot(targets, client=client, observed_at=OBSERVED_AT)

    assert fleet["status"] == "attention_required"
    assert fleet["findings"] == [
        {
            "code": "plugin_configuration_incomplete",
            "severity": "attention",
            "scope": "target",
            "target": "alpha",
            "observed_at": "2026-08-09T16:30:00Z",
            "source": "GET /api/runtime/status",
            "classification": "diagnostic",
            "evidence": {
                "plugins": [
                    {"id": "github", "name": "GitHub", "version": "0.4.0"},
                    {"id": "notes", "name": "Notes", "version": "0.2.0"},
                ]
            },
            "safe_next_inspection": "Inspect this target's plugin settings for missing required configuration.",
        }
    ]
    rendered = json.dumps(fleet)
    assert "API_KEY" not in rendered
    assert "PRIVATE_PATH" not in rendered
    assert "Disabled" not in json.dumps(fleet["findings"])


@pytest.mark.asyncio
async def test_rejects_duplicate_target_ids_before_network_activity():
    requests: list[httpx.Request] = []

    async def unexpected_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    targets = [
        {"id": "same", "target_url": "https://one.test"},
        {"id": "same", "target_url": "https://two.test"},
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request)) as client:
        with pytest.raises(ValueError, match="duplicate target id"):
            await snapshot_module.collect_fleet_snapshot(targets, client=client)

    assert requests == []


@pytest.mark.asyncio
async def test_rejects_more_than_twenty_targets_before_network_activity():
    requests: list[httpx.Request] = []

    async def unexpected_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    targets = [{"id": f"target-{index}", "target_url": f"https://target-{index}.test"} for index in range(21)]
    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request)) as client:
        with pytest.raises(ValueError, match="at most 20 targets"):
            await snapshot_module.collect_fleet_snapshot(targets, client=client)

    assert requests == []


@pytest.mark.asyncio
async def test_malformed_runtime_evidence_isolated_to_one_target():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(
                200,
                json={"ok": True, "graph_compiled": True, "setup_complete": True, "ui": "none"},
            )
        if request.url.host == "bad.test":
            return httpx.Response(
                200,
                json={
                    "setup_complete": True,
                    "graph_loaded": True,
                    "version": "0.127.0",
                    "plugins": [],
                    "skills": {"count": "not-a-number"},
                    "mcp": {},
                    "warnings": [],
                },
            )
        return httpx.Response(
            200,
            json={
                "setup_complete": True,
                "graph_loaded": True,
                "version": "0.127.0",
                "plugins": [],
                "skills": {},
                "mcp": {},
                "warnings": [],
            },
        )

    targets = [
        {"id": "good", "target_url": "https://good.test"},
        {"id": "bad", "target_url": "https://bad.test"},
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fleet = await snapshot_module.collect_fleet_snapshot(targets, client=client, observed_at=OBSERVED_AT)

    assert [target["status"] for target in fleet["targets"]] == ["degraded", "ready"]
    assert fleet["targets"][0]["sources"]["runtime"] == {
        "source": "GET /api/runtime/status",
        "observed_at": "2026-08-09T16:30:00Z",
        "state": "unavailable",
        "http_status": 200,
        "error": "invalid runtime evidence",
    }
    assert fleet["summary"] == {
        "total": 2,
        "ready": 1,
        "not_ready": 0,
        "degraded": 1,
        "unreachable": 0,
    }
    assert fleet["findings"] == [
        {
            "code": "target_readiness_attention",
            "severity": "attention",
            "scope": "target",
            "target": "bad",
            "observed_at": "2026-08-09T16:30:00Z",
            "source": "GET /healthz and GET /api/runtime/status",
            "classification": "diagnostic",
            "evidence": {"status": "degraded"},
            "safe_next_inspection": (
                "Inspect the unavailable evidence source before drawing conclusions from the partial snapshot."
            ),
        }
    ]


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
        config={
            "targets": ["local=http://127.0.0.1:8123"],
            "target_tokens": json.dumps({"local": "secret"}),
            "timeout_seconds": 4,
        },
        register_tool=registered.append,
    )

    plugin.register(registry)

    assert [tool.name for tool in registered] == ["operator_snapshot"]
    assert registered[0].args == {}


@pytest.mark.asyncio
async def test_tool_parses_operator_configured_targets_and_secret_token_map(monkeypatch):
    plugin = _load_plugin(monkeypatch)
    collected = []

    async def fake_collect(targets, *, timeout_seconds):
        collected.append((targets, timeout_seconds))
        return {
            "schema_version": "operator.fleet_snapshot.v1",
            "status": "ready",
            "summary": {"total": 2, "ready": 2, "not_ready": 0, "degraded": 0, "unreachable": 0},
            "targets": [],
        }

    monkeypatch.setattr(plugin, "collect_fleet_snapshot", fake_collect, raising=False)
    tool = plugin._build_tool(
        {
            "targets": ["zeta=https://zeta.test", "alpha=https://alpha.test"],
            "target_tokens": json.dumps({"alpha": "alpha-secret", "zeta": "zeta-secret"}),
            "timeout_seconds": 7,
        }
    )

    result = json.loads(await tool.ainvoke({}))

    assert result["schema_version"] == "operator.fleet_snapshot.v1"
    assert collected == [
        (
            [
                {"id": "zeta", "target_url": "https://zeta.test", "token": "zeta-secret"},
                {"id": "alpha", "target_url": "https://alpha.test", "token": "alpha-secret"},
            ],
            7.0,
        )
    ]


@pytest.mark.asyncio
async def test_unconfigured_tool_returns_without_network_activity(monkeypatch):
    plugin = _load_plugin(monkeypatch)

    async def unexpected_network(*args, **kwargs):
        raise AssertionError("unconfigured tool attempted network activity")

    monkeypatch.setattr(plugin, "collect_fleet_snapshot", unexpected_network, raising=False)
    tool = plugin._build_tool({})

    result = json.loads(await tool.ainvoke({}))

    assert result == {
        "schema_version": "operator.fleet_snapshot.v1",
        "status": "not_configured",
        "error": "Configure operator_control.targets before inspecting the fleet.",
    }
