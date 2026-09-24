# Native Model Adapter Migration Validation

## Focused evidence

The current tree contains the conformance tests and their green results. The
historical pre-implementation RED run was not captured before the first
wrapper slice; no current test is being presented as retrospective RED
evidence.

- RED boundary and provider conformance:
  `poetry run pytest tests/test_native_model_adapter_migration.py -q` — 15
  fake-backed tests pass.
- Shared protocol and public exports:
  `poetry run pytest tests/test_external_adapter_protocol.py
  tests/test_import.py -q` — 19 tests pass.
- Support-matrix rows:
  `poetry run pytest tests/test_workflow_model_support_matrix.py -q` — 17 tests
  pass, including the three native-provider candidate rows.
- Provider regressions:
  `poetry run pytest tests/test_apple_foundation_models.py
  tests/test_local_models.py tests/test_mlx_models.py
  tests/test_external_adapter_registry.py -q` — 361 tests pass.
- Combined migration/protocol/provider/matrix command — 410 tests pass.
- Repository suite: an earlier run completed with 2,752 passed, 1 skipped, and
  7 deselected. A final rerun reproduced four unrelated Darwin/MPS host
  capability failures in `test_floorplan_svg_fixture.py`,
  `test_generation_worker_controllers.py`, and `test_local_model_runners.py`;
  no migration test failed.
- Static checks: `poetry run ruff check src tests` and `git diff --check` pass.
- Package gate: `poetry build` completed successfully for version `0.1.20`.

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
result, retry, or fallback. Sync adapters used through async workflows probe
health before submitting generation, avoiding recursive use of the bounded
worker pool.

## Deferred native-only capabilities

Registry configuration binding, default-provider routing, model downloads,
streaming, embeddings, multimodal output, persistent sessions, and native
callback tool execution remain deferred. The existing native factories remain
available until a separate parity/provenance decision authorizes removal.

## Final drift review

- The v1 protocol ID and descriptor digest algorithm are unchanged.
- The four factories are exported alongside, and do not replace, the existing
  native factories.
- No native provider is registered as a default, installed through the CLI, or
  bound through the installed-adapter registry.
- The implementation does not add model downloads, endpoint discovery,
  streaming, embeddings, multimodal output, persistent sessions, or callback
  tool execution to the external text protocol.
- The only open handoff item is T7.3: the repository-wide suite is blocked by
  four unrelated Darwin/MPS host-capability failures documented above.
