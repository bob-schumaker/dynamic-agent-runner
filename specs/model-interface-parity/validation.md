# Model Interface Tool-Parity Validation Receipt

Date: 2026-08-30

## Deterministic Closure Ledger

The YAML ledger is intentionally test-only and machine-readable. Every positive
row uses the shared semantic projection: scenario or variant, exposed schemas,
JSON-canonical normalized calls, invocation/results, completion, and error
category. Schemas are captured from each seam's first actual adapter-facing
request (or provider-bound equivalent). Interface, mode, and provider-specific
traces are excluded.

<!-- rumdl-disable MD013 -->

```yaml
scope: offline-controlled-tool-contract
result: passed
executor_nodes: &executor_nodes
  - tests/test_executor.py::test_model_interface_parity_s1_selects_only_create_record
  - tests/test_executor.py::test_model_interface_parity_sync_and_async_records_match
  - tests/test_executor.py::test_model_interface_parity_s5_sync_and_async_records_match
  - tests/test_executor.py::test_model_interface_parity_s2_valid_and_invalid_arguments
  - tests/test_executor.py::test_model_interface_parity_s3_continues_with_lookup_identifier
  - tests/test_executor.py::test_model_interface_parity_s4_reports_controlled_failure
  - tests/test_executor.py::test_model_interface_parity_s5_completes_without_a_tool
  - tests/test_executor.py::test_model_interface_parity_s6_rejects_malformed_normalized_call_before_dispatch
openai_nodes: &openai_nodes
  - tests/test_openai_client.py::test_model_interface_parity_openai_s1_uses_normalized_native_call
  - tests/test_openai_client.py::test_model_interface_parity_openai_native_scenarios
litellm_nodes: &litellm_nodes
  - tests/test_litellm_provider_adapter.py::test_model_interface_parity_litellm_native_scenarios
endpoint_nodes: &endpoint_nodes
  - tests/test_local_models.py::test_model_interface_parity_local_endpoint_native_scenarios
llama_nodes: &llama_nodes
  - tests/test_local_models.py::test_model_interface_parity_llama_cpp_native_scenarios
mlx_nodes: &mlx_nodes
  - tests/test_mlx_models.py::test_model_interface_parity_mlx_qwen3_owned_codec_native_scenarios
apple_nodes: &apple_nodes
  - tests/test_apple_foundation_models.py::test_model_interface_parity_apple_callback_native_scenarios
positive_rows:
  - {interface: executor_fake_adapter, mode: sync, nodes: *executor_nodes, result: passed}
  - {interface: executor_fake_adapter, mode: async, nodes: *executor_nodes, result: passed}
  - {interface: openai_scripted_client, mode: sync, nodes: *openai_nodes, result: passed}
  - {interface: openai_scripted_client, mode: async, nodes: *openai_nodes, result: passed}
  - {interface: litellm_scripted_completion, mode: sync, nodes: *litellm_nodes, result: passed}
  - {interface: litellm_scripted_completion, mode: async, nodes: *litellm_nodes, result: passed}
  - {interface: local_endpoint_recording_transport, mode: sync, nodes: *endpoint_nodes, result: passed}
  - {interface: local_endpoint_recording_transport, mode: async, nodes: *endpoint_nodes, result: passed}
  - {interface: llama_cpp_injected_backend, mode: sync, nodes: *llama_nodes, result: passed}
  - {interface: llama_cpp_injected_backend, mode: async, nodes: *llama_nodes, result: passed}
  - {interface: mlx_qwen3_owned_codec, mode: sync, nodes: *mlx_nodes, result: passed}
  - {interface: mlx_qwen3_owned_codec, mode: async, nodes: *mlx_nodes, result: passed}
  - {interface: apple_injected_callback_bridge, mode: async, nodes: *apple_nodes, result: passed}
negative_rows:
  - {interface: mlx_stock_backend, mode: sync, node: tests/test_mlx_models.py::test_model_interface_parity_stock_mlx_rejects_tools_before_dispatch, result: passed}
  - {interface: mlx_stock_backend, mode: async, node: tests/test_mlx_models.py::test_model_interface_parity_stock_mlx_rejects_tools_before_dispatch, result: passed}
scenarios: [S1, S2, S2-invalid, S2-wrong-type, S2-invalid-enum, S2-unknown, S2-malformed, S3, S4, S5, S6]
scoped_result: 143 passed
```

<!-- rumdl-enable MD013 -->

The explicit executor S1, I/O-blocker, S2, S3, S4, S5, and S6 nodes also ran
in the scoped command. The I/O blocker proved that socket connection, process
start, and local-model download seams fail before a parity test can use them.
Apple S4 retains its callback-native evidence: one request, a failed
`tool_finished` event, package-owned executor error, and no continuation.

## Commands and Results

<!-- rumdl-disable MD013 -->

```sh
poetry run pytest -q \
  tests/test_executor.py::test_model_interface_parity_s1_selects_only_create_record \
  tests/test_executor.py::test_model_interface_parity_io_blocker_rejects_every_external_seam \
  tests/test_executor.py::test_model_interface_parity_sync_and_async_records_match \
  tests/test_executor.py::test_model_interface_parity_s5_sync_and_async_records_match \
  tests/test_executor.py::test_model_interface_parity_s2_valid_and_invalid_arguments \
  tests/test_executor.py::test_model_interface_parity_s3_continues_with_lookup_identifier \
  tests/test_executor.py::test_model_interface_parity_s4_reports_controlled_failure \
  tests/test_executor.py::test_model_interface_parity_s5_completes_without_a_tool \
  tests/test_executor.py::test_model_interface_parity_s6_rejects_malformed_normalized_call_before_dispatch \
  tests/test_openai_client.py::test_model_interface_parity_openai_s1_uses_normalized_native_call \
  tests/test_openai_client.py::test_model_interface_parity_openai_native_scenarios \
  tests/test_litellm_provider_adapter.py::test_model_interface_parity_litellm_native_scenarios \
  tests/test_local_models.py::test_model_interface_parity_local_endpoint_native_scenarios \
  tests/test_local_models.py::test_model_interface_parity_llama_cpp_native_scenarios \
  tests/test_mlx_models.py::test_model_interface_parity_mlx_qwen3_owned_codec_native_scenarios \
  tests/test_mlx_models.py::test_model_interface_parity_stock_mlx_rejects_tools_before_dispatch \
  tests/test_apple_foundation_models.py::test_model_interface_parity_apple_callback_native_scenarios
# 143 passed

poetry run pytest -q tests/test_executor.py tests/test_openai_client.py tests/test_litellm_provider_adapter.py tests/test_local_models.py tests/test_mlx_models.py tests/test_apple_foundation_models.py
# 695 passed

poetry run pytest -q
# 1613 passed, 1 skipped, 6 deselected

poetry run ruff check src tests
poetry run ruff format --check src tests
# passed
```

<!-- rumdl-enable MD013 -->

## Separate Gates Deliberately Not Run

| Gate | Status | Reason and owner |
| --- | --- | --- |
| Approval interaction | not run | A separate deterministic coordinator/executor pass must cover deny, approve once, and approve for this run with `create_record`; it is not a no-approval interface-parity prerequisite. |
| Local-model competency | not run | Manual, eligible-host Qwen3 evidence is outside pytest and CI; the generic stock MLX backend remains intentionally unsupported. |
| Live/external acceptance | not run | Fastmail, MCP, OAuth, Apple eligible-Mac execution, and external mutations require their own authorized acceptance process and are prohibited by this suite. |

The live model-interface runner is available as a separately authorized
operator command. It uses the same S1--S6 tool catalog as this receipt and
only exposes in-memory controlled tools. Positive live acceptance, negative-row
separation, and manual observation receipts are owned by
[`../live-model-interface-acceptance/spec.md`](../live-model-interface-acceptance/spec.md).
It is not run as part of this receipt: set
`DAR_RUN_LIVE_MODEL_INTERFACE_MATRIX=1` and run
`scripts/run_live_model_interface_matrix.py` with one explicit target and its
model configuration. Existing Codex and Apple native tests are marked
`live_matrix` supporting rows.

No scoped test made a network request, authenticated, loaded/downloaded a model,
started a provider process, or invoked an external tool.
