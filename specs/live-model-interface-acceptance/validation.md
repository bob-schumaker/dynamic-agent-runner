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

## T5.1 Baseline Diagnostic Observation — 2026-08-30

The later authorized endpoint-only S1 diagnostic used the endpoint artifact
and revision recorded above with vLLM Metal 0.28.0, `qwen3_xml`, automatic
content-format detection, and auto tool choice. It observed two schema-valid,
identical `create_record` calls in both sync and async mode, followed by no
final text after their controlled results. Both row receipts record
`adapter_error: 0`; this is a behavioral mismatch for that exact baseline,
not an adapter-error conclusion.

This observation refines the earlier aggregate endpoint receipt, whose
adapter-error classification was produced before the endpoint-specific
diagnostic evidence was available. It does not establish a model, parser,
template, or DAR-adapter cause. T5.1 defines the bounded B0--B2 follow-up
needed to make that attribution.

## T5.1 B0--B2 Endpoint Diagnosis — 2026-08-30

Authorization scope: the cached endpoint artifact only; S1 sync and async;
temporary vLLM server lifecycle in the temporary Herdr workspace
`dar-t5-1-vllm`; opaque authorization reference `matrix-20260830`, retained
by DAR receipts only as a digest. The workspace and server were closed after
the run. The DAR endpoint base URL was `http://127.0.0.1:8011/v1`; the direct
control posted to its `/chat/completions` suffix.

All candidates used vLLM Metal 0.28.0, the pinned
`mlx-community/Qwen3-4B-Instruct-2507-nvfp4` revision
`111ab717db337468c86004a79bd9df19c6e3986d`, `qwen3_xml`, auto tool choice,
the tokenizer-provided template, and model generation defaults: temperature
0.7, top-k 20, and top-p 0.8. The direct control retained request digest
`85cf2c4e4f3f80e7d93a2e7a2aaf5c633e5b42d2879b88fe8c5db6bbe2e5faff` and
only the structural result shown below.

| Candidate | One-variable setting | Direct control | DAR S1 sync and async |
| --- | --- | --- | --- |
| B0 | automatic content format (detected `string`) | zero tool calls; final text present | two valid `create_record` invocations; no final completion; `behavioral_mismatch` |
| B1 | explicit `--chat-template-content-format string` | zero tool calls; final text present | two valid `create_record` invocations; no final completion; `behavioral_mismatch` |
| B2 | explicit `--chat-template-content-format openai` | zero tool calls; final text present | one valid `create_record` invocation; no final completion; `behavioral_mismatch` |

No B0--B2 candidate satisfies S1 in both DAR modes. The direct controls and
DAR runs both fail S1, but with different shapes, so this evidence does not
establish an endpoint/model-configuration cause or a DAR adapter discrepancy.
It supports no adapter modification. T5.2 remains the separate compatibility
resolution decision, limited to this artifact, vLLM version, and candidate set.

## Cross-target S1--S5 receipt completion — 2026-08-30

The manually gated S1--S5 receipt matrix now has one classified full receipt
for every supported target. All runs exposed only the shared in-memory
controlled tools. A completed receipt records an observation; it does not turn
a behavioral mismatch or adapter error into a DAR implementation defect.

| Target | Model / configuration | Receipt | Classification |
| --- | --- | --- | --- |
| `apple` | eligible system model; async only | `457e6abd88a14409a39f2027137abd8b` | 5 async `behavioral_mismatch`; 5 sync `skipped` as unsupported. Native callbacks entered DAR, but no qualifying final completion; S5 selected tools. Detailed controls are retained in `../apple-foundation-model-adapter/validation.md`. |
| `codex` | `gpt-5.4-mini` | `76c1569e7ce74e17a3babb3afbf9c195` | 10 passed. The runner emitted a non-fatal HTTP client shutdown warning after receipt emission. |
| `openai` | `gpt-5.4-mini` | `e79f7562529f493eb8607f5eff6adde6` | 10 passed. The runner emitted a non-fatal HTTP client shutdown warning after receipt emission. |
| `litellm` | `gpt-5.4-mini` via the configured LiteLLM target | `8a44e1b067464a749a45ab1e58f6424e` | 10 passed. |
| `endpoint` | pinned Qwen3 via vLLM Metal 0.28.0 with `qwen3_xml` | T4.2 receipt | 10 `adapter_error`; later T5.1 narrows S1 to behavioral mismatches for B0--B2. T5.2 remains open. |
| `mlx_qwen3` | pinned Qwen3 MLX helper | T4.2 receipt | 2 passed (S5 sync/async), 8 `adapter_error` (S1--S4 sync/async). |
| `llama_cpp` | cached Qwen2.5-3B-Instruct Q4_K_M GGUF with `chatml-function-calling` | T4.2 v5 receipt | 10 passed. |

The Codex, OpenAI, and LiteLLM receipts used the opaque
`cross-target-20260830` authorization reference, retained by the receipts only
as a digest. The temporary redacted local receipt files are not authoritative;
the identifiers and classifications above are the retained evidence.
