# Operator Control plugin

A standalone, disabled-by-default protoAgent plugin for normalized operator evidence.

The initial S1 slice exposes one zero-argument `operator_snapshot` tool. It inspects one operator-configured protoAgent target using only:

- `GET /healthz`
- `GET /api/runtime/status`

The result records source and observation time, preserves partial evidence when one endpoint fails, and allowlists output so bearer tokens and sensitive upstream fields do not leak.

## Status

Local S1 implementation for RomeoRaven/protoAgent issue #1. No public repository or upstream proposal has been created.

## Configure

```yaml
plugins:
  enabled: [operator_control]

operator_control:
  target_url: http://127.0.0.1:8123
  token: "" # store through the host secret path
  timeout_seconds: 5
```

The tool intentionally accepts no target argument. The operator chooses the target in configuration; the model only reads it.

## Verify

```bash
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest -q
```

See `PROTO.md` for architecture and safety boundaries.
