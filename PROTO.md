# PROTO.md — operator-control plugin

This is the canonical grounding file for work in this repository.

## Purpose and owner boundary

This standalone protoAgent plugin is the durable owner for the operator-control-plane capability tracked by RomeoRaven/protoAgent issue #1. It is not protoAgent core.

`PROTO.md` is this repository's single agent-grounding source. Ordinary discovery surfaces such as `README.md` point here, matching the AOS pointer model. Do not add `AGENTS.md` or `CLAUDE.md` pointer copies by convention; those high-power instruction surfaces require a separate, explicit repository decision.

The current 0.3 slice inspects up to 20 explicitly configured protoAgent targets concurrently through their existing read-only HTTP contracts, returns deterministic source-attributed fleet evidence, and emits one truthful attention finding when observed runtime versions differ.

Do not add fleet writes, config mutation, process control, consent execution, broad alert policy, dashboards, writable target registries, or upstream-core changes to this slice.

## Runtime shape

- Python 3.11+
- Host-provided `langchain-core` and `httpx`
- External plugin entry: `register(registry)` in root `__init__.py`
- Manifest/config owner: `protoagent.plugin.yaml`, section `operator_control`
- Ships disabled; enablement is the operator's trust decision
- `targets` is an operator-visible list of `id=url` entries
- `target_tokens` is a host-routed secret JSON object mapping target IDs to independent bearers
- Target bearers must never enter returned evidence

## Safety contract

- The agent-facing tool takes zero arguments. Target IDs, URLs, and bearers come only from operator configuration; the model cannot redirect the probe.
- The configured fleet is bounded to 20 targets and duplicate IDs fail before network activity.
- Target URLs must use HTTP(S) and cannot embed credentials.
- Target interaction is GET-only: `/healthz` and `/api/runtime/status`.
- Targets are collected concurrently; output is sorted by target ID so completion order cannot change the contract.
- A version-skew finding is an `attention` signal sourced from available runtime evidence. It reports observed version groups but never guesses which target is outdated or which version is intended.
- A fleet with consistent observed versions emits no version-skew finding; broader severity, ranking, deduplication, and alert policy belong to a later issue #6 slice.
- Fleet status is only `ready` or `attention_required`.
- Output is an allowlisted projection. Never pass through raw target JSON, model identity, instance UID, filesystem paths, MCP server config/environment, or auth values.
- One failed source must not erase evidence from another source; one failed target must not erase evidence from another target.
- Every source records endpoint, observation time, availability, and HTTP status.
- `/healthz` HTTP 503 is valid negative readiness evidence, not a transport failure.

## Acceptance criteria

1. Given ready, not-ready, and unreachable configured targets, when `operator_snapshot` runs, then it performs only the two declared GET requests per target and returns deterministic per-target evidence plus a fleet summary.
2. Given configuration order or request completion order differs, when the fleet snapshot completes, then targets remain sorted by stable operator ID and counts remain deterministic.
3. Given one endpoint or target fails, when the snapshot completes, then evidence from other sources and targets remains and the fleet state is `attention_required`.
4. Given a not-yet-ready target, when `/healthz` returns its documented 503 JSON and runtime status remains readable, then that target is `not_ready` and health remains an available source.
5. Given per-target bearer auth or sensitive fields in upstream payloads, when evidence is rendered, then none of those values are present.
6. Given duplicate IDs or more than 20 targets, when collection is requested, then configuration fails before network activity.
7. Given no configured targets, when the tool runs, then it returns a clear `not_configured` result without network activity.
8. Given two or more observed runtime versions, when the fleet snapshot completes, then one deterministic `fleet_version_skew` attention signal groups target IDs by exact version and attributes the evidence to `GET /api/runtime/status`.
9. Given all comparable targets report one version, when the fleet snapshot completes, then no version-skew finding is manufactured.

## Commands

```bash
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest -q
```

Run the suite standalone. For host integration, load the plugin through the current protoAgent `graph.plugins.loader` with an isolated plugin root; do not edit a live instance's plugin config merely to test loading.

## Files

- `snapshot.py` — URL/target validation, concurrent GET collection, allowlisted normalization, deterministic fleet summary, and bounded version-skew finding
- `__init__.py` — zero-argument `operator_snapshot` tool, host config parsing, and plugin registration
- `protoagent.plugin.yaml` — disabled-by-default manifest, target list, and secret token-map schema
- `tests/test_snapshot.py` — behavior/security contract
- `tests/test_packaging.py` — manifest/version/safety lockstep

## Development rules

- Use RED → GREEN → REFACTOR for behavior changes.
- Keep host imports out of module top level except host-provided runtime libraries.
- Keep `pyproject.toml` and manifest versions in lockstep.
- Prefer composing stable public protoAgent surfaces over importing core implementation modules.
- Do not add target selection as a tool argument; changing the configured fleet is an operator decision.
