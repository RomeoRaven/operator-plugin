"""protoAgent operator-control plugin: read-only configured-fleet snapshot."""

from __future__ import annotations

import json

from langchain_core.tools import tool

if __package__:
    from .snapshot import collect_fleet_snapshot
else:  # Standalone pytest imports the root entry as top-level ``__init__``.
    from snapshot import collect_fleet_snapshot


def _configured_targets(config: dict) -> list[dict[str, str]]:
    raw_targets = config.get("targets") or []
    if not isinstance(raw_targets, (list, tuple)):
        raise ValueError("operator_control.targets must be a list of id=url entries")

    raw_tokens = str(config.get("target_tokens") or "").strip()
    if raw_tokens:
        try:
            token_map = json.loads(raw_tokens)
        except json.JSONDecodeError as exc:
            raise ValueError("operator_control.target_tokens must be a JSON object") from exc
        if not isinstance(token_map, dict):
            raise ValueError("operator_control.target_tokens must be a JSON object")
    else:
        token_map = {}

    targets: list[dict[str, str]] = []
    for raw_entry in raw_targets:
        target_id, separator, target_url = str(raw_entry or "").partition("=")
        target_id = target_id.strip()
        target_url = target_url.strip()
        if not separator or not target_id or not target_url:
            raise ValueError("each operator_control.targets entry must use id=url")
        token = token_map.get(target_id, "")
        if not isinstance(token, str):
            raise ValueError(f"token for target {target_id!r} must be a string")
        targets.append({"id": target_id, "target_url": target_url, "token": token})

    unknown_token_ids = sorted(set(token_map) - {target["id"] for target in targets})
    if unknown_token_ids:
        raise ValueError(f"target_tokens contains unknown target ids: {', '.join(unknown_token_ids)}")
    return targets


def _build_tool(config: dict):
    @tool
    async def operator_snapshot() -> str:
        """Inspect the configured protoAgent fleet and return normalized live evidence.

        This tool is read-only: it performs GET requests to `/healthz` and
        `/api/runtime/status`. Configured bearer tokens are never returned.
        """
        try:
            targets = _configured_targets(config)
            if not targets:
                return json.dumps(
                    {
                        "schema_version": "operator.fleet_snapshot.v1",
                        "status": "not_configured",
                        "error": "Configure operator_control.targets before inspecting the fleet.",
                    }
                )
            timeout = float(config.get("timeout_seconds") or 5)
            result = await collect_fleet_snapshot(targets, timeout_seconds=timeout)
        except (TypeError, ValueError) as exc:
            return json.dumps(
                {
                    "schema_version": "operator.fleet_snapshot.v1",
                    "status": "configuration_error",
                    "error": str(exc),
                }
            )
        return json.dumps(result, indent=2, sort_keys=True)

    return operator_snapshot


def register(registry) -> None:
    """Register the single read-only operator snapshot tool."""
    registry.register_tool(_build_tool(dict(getattr(registry, "config", None) or {})))
