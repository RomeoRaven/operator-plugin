"""Read-only evidence collection for one configured protoAgent target."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

_SCHEMA_VERSION = "operator.snapshot.v1"
_FLEET_SCHEMA_VERSION = "operator.fleet_snapshot.v1"
_MAX_TARGETS = 20
_ENDPOINTS = {"health": "/healthz", "runtime": "/api/runtime/status"}


def _timestamp(value: datetime | None) -> str:
    observed = value or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return observed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_base_url(raw: str) -> str:
    parsed = urlsplit(str(raw or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("target_url must use http or https and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("target_url must not contain credentials; configure token separately")
    if parsed.query or parsed.fragment:
        raise ValueError("target_url must not contain a query or fragment")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _safe_plugins(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    allowed = ("id", "name", "version", "enabled", "incomplete")
    for raw in value:
        if not isinstance(raw, dict) or not str(raw.get("id", "")).strip():
            continue
        out.append({key: raw[key] for key in allowed if key in raw})
    return out


def _safe_health(payload: Any) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    allowed = ("ok", "graph_compiled", "setup_complete", "ui")
    return {key: raw[key] for key in allowed if key in raw}


def _safe_runtime(payload: Any) -> dict[str, Any]:
    raw: dict[str, Any] = payload if isinstance(payload, dict) else {}
    raw_skills = raw.get("skills")
    raw_mcp = raw.get("mcp")
    raw_warnings = raw.get("warnings")
    skills: dict[str, Any] = raw_skills if isinstance(raw_skills, dict) else {}
    mcp: dict[str, Any] = raw_mcp if isinstance(raw_mcp, dict) else {}
    warnings: list[Any] = raw_warnings if isinstance(raw_warnings, list) else []
    return {
        "setup_complete": bool(raw.get("setup_complete")),
        "graph_loaded": bool(raw.get("graph_loaded")),
        "version": str(raw.get("version") or ""),
        "plugins": _safe_plugins(raw.get("plugins")),
        "skills": {
            "enabled": bool(skills.get("enabled")),
            "count": int(skills.get("count") or 0),
        },
        "mcp": {
            "enabled": bool(mcp.get("enabled")),
            "tool_count": int(mcp.get("tool_count") or 0),
        },
        "warning_count": len(warnings),
    }


async def _read_source(
    client: httpx.AsyncClient,
    *,
    name: str,
    path: str,
    base_url: str,
    headers: dict[str, str],
    observed_at: str,
) -> dict[str, Any]:
    source = f"GET {path}"
    try:
        response = await client.get(base_url + path, headers=headers)
    except httpx.HTTPError as exc:
        return {
            "source": source,
            "observed_at": observed_at,
            "state": "unavailable",
            "http_status": None,
            "error": str(exc)[:200] or type(exc).__name__,
        }

    if response.status_code >= 400 and not (name == "health" and response.status_code == 503):
        return {
            "source": source,
            "observed_at": observed_at,
            "state": "unavailable",
            "http_status": response.status_code,
            "error": f"HTTP {response.status_code}",
        }

    try:
        payload = response.json()
    except ValueError:
        return {
            "source": source,
            "observed_at": observed_at,
            "state": "unavailable",
            "http_status": response.status_code,
            "error": "invalid JSON response",
        }

    try:
        evidence = _safe_health(payload) if name == "health" else _safe_runtime(payload)
    except (TypeError, ValueError, OverflowError):
        return {
            "source": source,
            "observed_at": observed_at,
            "state": "unavailable",
            "http_status": response.status_code,
            "error": f"invalid {name} evidence",
        }
    return {
        "source": source,
        "observed_at": observed_at,
        "state": "available",
        "http_status": response.status_code,
        "evidence": evidence,
    }


def _overall_status(sources: dict[str, dict[str, Any]]) -> str:
    available = [source for source in sources.values() if source["state"] == "available"]
    if not available:
        return "unreachable"
    if len(available) != len(sources):
        return "degraded"

    health = sources["health"]["evidence"]
    runtime = sources["runtime"]["evidence"]
    if health.get("ok") is True and runtime.get("graph_loaded") is True:
        return "ready"
    return "not_ready"


async def collect_snapshot(
    target_url: str,
    *,
    token: str = "",
    timeout_seconds: float = 5,
    client: httpx.AsyncClient | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Collect a normalized, secret-free live snapshot without writing to the target.

    Acceptance criteria:
    - Given one configured target, only GET health/runtime requests are made.
    - Given one failed endpoint, its failure is isolated and retained as provenance.
    - Given bearer auth, the token is sent but never copied into returned evidence.
    """
    base_url = _normalize_base_url(target_url)
    observed = _timestamp(observed_at)
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def collect(active_client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
        health, runtime = await asyncio.gather(
            _read_source(
                active_client,
                name="health",
                path=_ENDPOINTS["health"],
                base_url=base_url,
                headers=headers,
                observed_at=observed,
            ),
            _read_source(
                active_client,
                name="runtime",
                path=_ENDPOINTS["runtime"],
                base_url=base_url,
                headers=headers,
                observed_at=observed,
            ),
        )
        return {"health": health, "runtime": runtime}

    if client is None:
        timeout = max(1.0, min(float(timeout_seconds), 30.0))
        async with httpx.AsyncClient(timeout=timeout) as owned_client:
            sources = await collect(owned_client)
    else:
        sources = await collect(client)

    return {
        "schema_version": _SCHEMA_VERSION,
        "target": {"base_url": base_url},
        "observed_at": observed,
        "freshness": "live",
        "status": _overall_status(sources),
        "sources": sources,
    }


async def collect_fleet_snapshot(
    targets: list[dict[str, Any]],
    *,
    timeout_seconds: float = 5,
    client: httpx.AsyncClient | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Collect one deterministic read-only snapshot across configured targets."""
    if len(targets) > _MAX_TARGETS:
        raise ValueError(f"configure at most {_MAX_TARGETS} targets")
    observed_value = observed_at or datetime.now(timezone.utc)
    normalized = sorted(
        (
            {
                "id": str(target.get("id") or "").strip(),
                "target_url": _normalize_base_url(str(target.get("target_url") or "")),
                "token": str(target.get("token") or ""),
            }
            for target in targets
        ),
        key=lambda target: target["id"],
    )
    target_ids = [target["id"] for target in normalized]
    if len(target_ids) != len(set(target_ids)):
        raise ValueError("duplicate target id")

    async def collect(active_client: httpx.AsyncClient) -> list[dict[str, Any]]:
        snapshots = await asyncio.gather(
            *(
                collect_snapshot(
                    target["target_url"],
                    token=target["token"],
                    client=active_client,
                    observed_at=observed_value,
                )
                for target in normalized
            )
        )
        for target, snapshot in zip(normalized, snapshots, strict=True):
            snapshot["target"] = {
                "id": target["id"],
                "base_url": snapshot["target"]["base_url"],
            }
        return snapshots

    if client is None:
        timeout = max(1.0, min(float(timeout_seconds), 30.0))
        async with httpx.AsyncClient(timeout=timeout) as owned_client:
            snapshots = await collect(owned_client)
    else:
        snapshots = await collect(client)

    counts = {status: 0 for status in ("ready", "not_ready", "degraded", "unreachable")}
    for snapshot in snapshots:
        counts[snapshot["status"]] += 1

    return {
        "schema_version": _FLEET_SCHEMA_VERSION,
        "observed_at": _timestamp(observed_value),
        "freshness": "live",
        "status": "ready" if counts["ready"] == len(snapshots) else "attention_required",
        "summary": {"total": len(snapshots), **counts},
        "targets": snapshots,
    }
