# Native Model Adapter Migration Validation

## Focused evidence

- RED boundary and provider conformance:
  `poetry run pytest tests/test_native_model_adapter_migration.py -q` — 3
  fake-backed tests pass.
- Shared protocol and public exports:
  `poetry run pytest tests/test_external_adapter_protocol.py
  tests/test_import.py -q` — 19 tests pass.
- Support-matrix rows:
  `poetry run pytest tests/test_workflow_model_support_matrix.py -q` — 16 tests
  pass, including the three native-provider candidate rows.
- Provider regressions:
  `poetry run pytest tests/test_apple_foundation_models.py
  tests/test_local_models.py tests/test_mlx_models.py
  tests/test_external_adapter_registry.py -q` — 361 tests pass.
- Repository suite: `poetry run pytest -q` — 2,752 passed, 1 skipped, 7 deselected.
- Static checks: `poetry run ruff check src tests` and `git diff --check` pass.

## Capability and boundary results

| Provider | Mode | Structured output | Tools | Health |
| --- | --- | --- | --- | --- |
| Apple Foundation Models | async | advertised from native binding | omitted because callback bridge is native-only | OS/SDK/model preflight, redacted |
| llama.cpp | sync | advertised for the direct chat path | only `chatml-function-calling` configuration | prepared path/backend readiness, redacted |
| MLX | sync or async | text-only | exact versioned `MLXToolCodec` plus backend support | platform/material/backend readiness, redacted |

The façade owns generic admission, JSON-schema validation, bounded health,
deadline/cancellation handling, response normalization, tracing, and removal.
The wrappers never receive tool handlers, approval objects, or callbacks. Late
blocking native work remains bounded by the façade worker and produces no late
result, retry, or fallback.

## Deferred native-only capabilities

Registry configuration binding, default-provider routing, model downloads,
streaming, embeddings, multimodal output, persistent sessions, and native
callback tool execution remain deferred. The existing native factories remain
available until a separate parity/provenance decision authorizes removal.
