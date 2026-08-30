# Live Model-Interface Acceptance Receipt

Date: 2026-08-30

## Run Boundary

All commands were manually enabled with
`DAR_RUN_LIVE_MODEL_INTERFACE_MATRIX=1`. They used only the shared in-memory
controlled tools. The vLLM server ran inside the temporary Herdr workspace
`dar-live-vllm-matrix` and was stopped after its run. Approval-interaction
coverage was not included.

The initial runner still applies all S1--S6 rows and fails on its first unmet
expectation. These are discovery observations, not acceptance results under the
new positive-only contract; the implementation checklist in `spec.md` defines
what must change before a full acceptance receipt can be claimed.

## Observations

| Target | Model / configuration | First observed outcome | Classification for follow-up |
| --- | --- | --- | --- |
| OpenAI-compatible endpoint (vLLM 0.28.0 Metal) | `mlx-community/Qwen3-4B-Instruct-2507-nvfp4` at revision `111ab717db337468c86004a79bd9df19c6e3986d`; `qwen3_xml` parser and auto-tool choice enabled | S1 returned HTTP 200 but DAR observed no `create_record` call | behavioral mismatch; retain prompt/parser/request evidence before assigning an adapter bug |
| Direct MLX | same Qwen3 artifact | S1 observed no `create_record` call | behavioral mismatch; local-codec/prompt investigation |
| Direct llama.cpp | cached Qwen2.5-3B Q4_K_M GGUF | S1 observed no `create_record` call | behavioral mismatch; prompt/template/parser investigation |
| Codex | `gpt-5.4-mini` | S1 and S2 progressed; S2-invalid did not yield `validation_error` | expected limitation of the old live-negative criterion |
| OpenAI | `gpt-5.4-mini` | S1 and S2 progressed; S2-invalid did not yield `validation_error` | expected limitation of the old live-negative criterion |
| LiteLLM | `gpt-5.4-mini` | S1 observed no expected tool path | behavioral mismatch; capture transport/request diagnostics |
| Apple Foundation Models | eligible system model | wrapper construction raised `GenerationError(status: 255)`: `Failed to create bridged tool: DarTool2Arguments contains undefined references: [Annotated]` | Apple bridge implementation regression; canonical task B5.1 |

## Interpretation

The Codex/OpenAI S2-invalid outcomes validate the scope split: those models
completed positive behavior but did not deliberately generate the prescribed
invalid payload. The endpoint, MLX, llama.cpp, and LiteLLM S1 outcomes require
compatibility evidence before a runtime change is specified. The Apple failure
occurs while DAR constructs the SDK bridge wrapper, before model behavior is
measured, and is therefore tracked as a bug task.

## T4.2 Authorized Live Receipt — 2026-08-30

Authorization scope: cached local artifacts only; endpoint, `mlx_qwen3`, and
`llama_cpp`; sync and async; S1--S5; vLLM lifecycle started and stopped in the
temporary Herdr workspace `dar-live-vllm-t4-2`; opaque authorization reference
provided as `matrix-20260830` and retained by each receipt only as a digest.

| Target | Artifact | Receipt status | Row counts | Lifecycle result |
| --- | --- | --- | --- | --- |
| endpoint | `mlx-community/Qwen3-4B-Instruct-2507-nvfp4` revision `111ab717db337468c86004a79bd9df19c6e3986d`, local vLLM with `qwen3_xml` | `adapter_error` | 10 adapter errors | vLLM started by `vllm-metalctl` in Herdr and stopped afterward |
| `mlx_qwen3` | same pinned Qwen3 MLX artifact | `adapter_error` | 2 passed (S5 sync/async), 8 adapter errors (S1--S4 sync/async) | in-process only |
| `llama_cpp` | cached `Qwen2.5-3B-Instruct` Q4_K_M GGUF with llama.cpp `chatml-function-calling` | `passed` | 10 passed (S1--S5 sync/async) | in-process only |

These are classified observations, not evidence that any model artifact alone
is defective. The final llama.cpp rerun uses the handler's native function-call
grammar, adapts DAR's flat tool schema at the handler boundary, and renders
tool results in the handler's supported message form. Its v5 receipt records
all ten rows as passed.
