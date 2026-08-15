# Operator Control plugin

A standalone, disabled-by-default protoAgent plugin for normalized operator evidence across a small configured fleet.

The 0.5 S1 slice exposes one zero-argument `operator_snapshot` tool. It concurrently inspects up to 20 operator-configured protoAgent targets using only:

- `GET /healthz`
- `GET /api/runtime/status`

The result records source and observation time, preserves partial evidence when an endpoint or target fails, sorts targets by stable operator ID, and allowlists output so bearer tokens and sensitive upstream fields do not leak.

Bounded findings currently cover:

- unreachable, degraded, or not-ready targets, reported as observed readiness diagnostics without changing the target;
- exact runtime-version skew, grouped by target without guessing the intended version;
- enabled plugins explicitly reported `incomplete`, attributed to the target and limited to plugin ID, name, and version.

Ready, version-consistent fleets with no incomplete enabled plugins stay quiet. Raw required-config keys, loader errors, tracebacks, trust judgments, and update recommendations are not exposed.

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

## Platform evidence

Minimum declared protoAgent version: **0.131.3**. The Phase A qualification host
candidate is RR protoAgent **0.136.0** at
`1d80d15e229ac51a419b53c3378db1bea4796379`.

CI coverage (not current-head proof): GitHub Actions is configured to gate pull
requests and pushes to main with Ruff and standalone pytest on Linux, native
Windows, and macOS. Acceptance must read back the checks for the exact candidate
commit.

| Platform | Current evidence | Limitation / owner |
|---|---|---|
| Linux | Configured gate: Ruff and standalone pytest | Exact-head install/load/lifecycle acceptance remains separately tracked in [RR pA #1](https://github.com/RomeoRaven/protoAgent/issues/1) and the Operator Stack |
| Windows | Configured native gate: Ruff and standalone pytest | PC1 install/load/lifecycle acceptance is **Not tested** and remains owned by [RR pA #14](https://github.com/RomeoRaven/protoAgent/issues/14) |
| macOS | Configured gate: Ruff and standalone pytest | Installed-runtime acceptance is **Not tested** |

Current exact-head installed-runtime acceptance: **Not tested**. CI evidence is
source/standalone evidence, not a tagged release or real pA lifecycle. This
matrix is not PC1 acceptance.

## License

[MIT](LICENSE)
