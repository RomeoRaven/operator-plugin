# Operator Control plugin

A standalone, disabled-by-default protoAgent plugin for normalized operator evidence across a small configured fleet.

The 0.2 S1 slice exposes one zero-argument `operator_snapshot` tool. It concurrently inspects up to 20 operator-configured protoAgent targets using only:

- `GET /healthz`
- `GET /api/runtime/status`

The result records source and observation time, preserves partial evidence when an endpoint or target fails, sorts targets by stable operator ID, and allowlists output so bearer tokens and sensitive upstream fields do not leak.

## Status

S1-first implementation for [RomeoRaven/protoAgent issue #1](https://github.com/RomeoRaven/protoAgent/issues/1), published in the RR-owned [`RomeoRaven/operator-plugin`](https://github.com/RomeoRaven/operator-plugin) repository. Merge, release, and any upstream protoLabsAI proposal remain separate decisions.

## Configure

```yaml
plugins:
  enabled: [operator_control]

operator_control:
  targets:
    - s1=http://127.0.0.1:8123
    - lab=https://lab.example.test
  target_tokens: '{"s1":"first-bearer","lab":"second-bearer"}' # store through the host secret path
  timeout_seconds: 5
```

Each target entry is `id=url`. `target_tokens` is an optional JSON object keyed by those IDs and is declared as one host-routed secret because protoAgent secret routing is top-level-key based. The tool intentionally accepts no target arguments: the operator chooses the bounded fleet in configuration; the model only reads it. Duplicate IDs and fleets above 20 fail before network activity.

## Verify

```bash
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest -q
```

See `PROTO.md` for architecture and safety boundaries.
