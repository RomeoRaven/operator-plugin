"""protoAgent operator-control plugin: one read-only local-instance snapshot."""

from __future__ import annotations

import json

from langchain_core.tools import tool

if __package__:
    from .snapshot import collect_snapshot
else:  # Standalone pytest imports the root entry as top-level ``__init__``.
    from snapshot import collect_snapshot


def _build_tool(config: dict):
    @tool
    async def operator_snapshot() -> str:
        """Inspect the one configured protoAgent target and return normalized live evidence.

        This tool is read-only: it performs GET requests to `/healthz` and
        `/api/runtime/status`. The configured bearer token is never returned.
        """
        target_url = str(config.get("target_url") or "").strip()
        if not target_url:
            return json.dumps(
                {
                    "schema_version": "operator.snapshot.v1",
                    "status": "not_configured",
                    "error": "Configure operator_control.target_url before inspecting a target.",
                }
            )
        try:
            timeout = float(config.get("timeout_seconds") or 5)
            result = await collect_snapshot(
                target_url,
                token=str(config.get("token") or ""),
                timeout_seconds=timeout,
            )
        except (TypeError, ValueError) as exc:
            return json.dumps(
                {
                    "schema_version": "operator.snapshot.v1",
                    "status": "configuration_error",
                    "error": str(exc),
                }
            )
        return json.dumps(result, indent=2, sort_keys=True)

    return operator_snapshot


def register(registry) -> None:
    """Register the single read-only operator snapshot tool."""
    registry.register_tool(_build_tool(dict(getattr(registry, "config", None) or {})))
