# PROTO.md — operator-control plugin

This is the canonical grounding file for work in this repository.

## Purpose and owner boundary

This standalone protoAgent plugin is the durable owner for the operator-control-plane capability tracked by RomeoRaven/protoAgent issue #1. It is not protoAgent core.

`PROTO.md` is this repository's single agent-grounding source. Ordinary discovery surfaces such as `README.md` point here, matching the AOS pointer model. Do not add `AGENTS.md` or `CLAUDE.md` pointer copies by convention; those high-power instruction surfaces require a separate, explicit repository decision.

The current 0.1 slice intentionally does one thing: from a dedicated operator workspace, inspect one explicitly configured protoAgent target through its existing read-only HTTP contracts and return normalized, source-attributed live evidence.

Do not add fleet writes, config mutation, process control, consent execution, dashboards, durable target registries, or upstream-core changes to this slice.

## Runtime shape

- Python 3.11+
- Host-provided `langchain-core` and `httpx`
- External plugin entry: `register(registry)` in root `__init__.py`
- Manifest/config owner: `protoagent.plugin.yaml`, section `operator_control`
- Ships disabled; enablement is the operator's trust decision
- The target bearer is a declared secret and must never enter returned evidence

## Safety contract

- The agent-facing tool takes zero arguments. Target URL and bearer come only from operator configuration; the model cannot redirect the probe.
- Target URLs must use HTTP(S) and cannot embed credentials.
- Target interaction is GET-only: `/healthz` and `/api/runtime/status`.
- Output is an allowlisted projection. Never pass through raw target JSON, model identity, instance UID, filesystem paths, MCP server config/environment, or auth values.
- One failed source must not erase evidence from another source.
- Every source records endpoint, observation time, availability, and HTTP status.
- `/healthz` HTTP 503 is valid negative readiness evidence, not a transport failure.

## Acceptance criteria

1. Given a healthy target, when `operator_snapshot` runs, then it performs only the two declared GET requests and returns `ready` with normalized health/runtime evidence.
2. Given one endpoint fails, when the snapshot completes, then evidence from the other endpoint remains and the overall state is `degraded`.
3. Given a not-yet-ready target, when `/healthz` returns its documented 503 JSON and runtime status remains readable, then the overall state is `not_ready` and health remains an available source.
4. Given configured bearer auth or sensitive fields in upstream payloads, when evidence is rendered, then none of those values are present.
5. Given no configured target, when the tool runs, then it returns a clear `not_configured` result without network activity.

## Commands

```bash
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest -q
```

Run the suite standalone. For host integration, load the plugin through the current protoAgent `graph.plugins.loader` with an isolated plugin root; do not edit a live instance's plugin config merely to test loading.

## Files

- `snapshot.py` — URL validation, GET collection, allowlisted normalization, overall state
- `__init__.py` — zero-argument `operator_snapshot` tool and plugin registration
- `protoagent.plugin.yaml` — disabled-by-default manifest and secret-bearing config schema
- `tests/test_snapshot.py` — behavior/security contract
- `tests/test_packaging.py` — manifest/version/safety lockstep

## Development rules

- Use RED → GREEN → REFACTOR for behavior changes.
- Keep host imports out of module top level except host-provided runtime libraries.
- Keep `pyproject.toml` and manifest versions in lockstep.
- Prefer composing stable public protoAgent surfaces over importing core implementation modules.
- Do not add a target URL as a tool argument; changing targets is an operator configuration decision.
