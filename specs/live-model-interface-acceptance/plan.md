# Live Model-Interface Acceptance Implementation Plan

## Metadata

- Status: T5.1 endpoint diagnosis complete; T5.2 compatibility resolution
  pending in `tasks.md`
- Governing spec: `spec.md`
- Parent deterministic contract: `../model-interface-parity/spec.md`
- Delivery target: this repository's working tree at
  `/Users/roschuma/Repos/roschuma/dynamic-agent-runner`
- Implementation route: the ordered TDD tasks in `tasks.md`, using the existing
  pytest corpus and manual runner only
- Decision: the user explicitly requested this plan and its readiness review on
  2026-08-30. The feature moves from light to guided mode because it has a
  standalone plan and task list. Implementation remains bounded by the ordered
  tasks and stated manual gate.

## Objective and Boundaries

Implement the manually gated positive acceptance protocol without changing the
deterministic S1--S6 parity contract, provider adapters, model prompting,
server lifecycle, or approval behavior. The outcome is a classified JSON receipt
for one target. Ordinary pytest remains fake-backed and offline.

| Surface | Responsibility |
| --- | --- |
| `tests/model_interface_matrix.py` | Keep the harmless S1--S6 catalog and expose the fixed S1--S5 live-positive subset. |
| `scripts/run_live_model_interface_matrix.py` | Validate eligibility, execute all selected rows, classify outcomes, and render the receipt. |
| `tests/test_model_interface_matrix.py` | Test selection, continuation, classification, aggregation, and safe diagnostics with fakes only. |
| `validation.md` | Retain later manually authorized receipts; it is not automated test evidence. |

No package module, dependency, provider-specific diagnostic interface, or
automated vLLM/MLX/llama.cpp lifecycle is required.

### T5.1 bounded endpoint diagnosis

T5.1 is a manual, post-delivery compatibility diagnosis. It tests only B0--B2
defined in `tasks.md`: the recorded `qwen3_xml` baseline and the two documented
content-format overrides. It freezes the model revision, parser, template
source, tool policy, and generation settings, changes one setting per candidate,
and uses a temporary server without changing the installed launchd definition.

Each candidate begins with a same-scenario direct OpenAI-compatible endpoint
control, including the post-tool-result continuation, then runs DAR S1 in sync
and async mode. The retained direct evidence is structural and redacted; it is
not a new package capture interface or receipt format. Matching direct and DAR
invalid shapes establish an endpoint/model-configuration observation. A direct
S1 pass paired with a DAR miss establishes an adapter discrepancy and requires
a separately scoped test-first task. The task cannot infer a result beyond its
three named candidates.

## Technical Design

### Selection and eligibility

Leave `controlled_tool_scenarios()` unchanged: deterministic parity owns invalid
and malformed rows. Add a narrow live-positive selector that accepts exactly
`S1`, `S2`, `S3`, `S4`, and `S5`; reject every other `--scenario` value before
adapter construction or provider activity.

Keep a small runner-local mapping adjacent to `_TARGETS` for target id, eligible
modes, and required non-secret arguments. Apple is async-only. With `--mode
both`, emit one `skipped` `unsupported_mode` row for Apple sync and execute its
async rows; each selected scenario receives that skipped sync row. Never route
its async adapter through sync execution.

Keep the existing `_adapter(arguments, asynchronous=...)` factory as the only
target-to-adapter route. The runner continues to use `execute_workflow` or
`execute_workflow_async` with strict coverage. This work only adds eligibility,
observation, and receipt behavior around that established route; it does not
change any provider factory or executor selection policy.

### Row execution and receipt

Replace fail-fast `_run_scenario()` with four private, script-local helpers:
side-effect-free `_preflight()`, `_planned_rows()`, a generic recording adapter
facade, and pure `_classify_row()`/`_summarize()` functions. Keep their values
as ordinary JSON-safe dictionaries; no package module or persistence layer is
needed.

`_preflight()` validates opt-in, required non-secret arguments, target/mode
eligibility, and safe path existence/readability. It must not construct an
adapter, import an optional SDK, load a model, read auth, contact a provider,
download, or manage a server. A failed preflight creates `unavailable` rows
without calling adapter or executor code. Adapter construction and provider
availability failures after preflight are row-local `adapter_error` outcomes.

The generic recording facade delegates unchanged at DAR's existing adapter
request boundary. For every request turn it records ordinal, actual exposed-tool
declaration/tool-choice policy digest, bounded adapter-facing message/result
context digest, and returned normalized `ModelToolCall` projection. The row
builder records the final `WorkflowResult` projection. Neither retains raw
provider responses or introduces provider-specific behavior.

Before receipt hashing, project every observed adapter request into the common
contract shape: exposed controlled tool IDs plus canonical input schemas,
initial/continuation tool-choice semantics, and the prior controlled tool-result
presence for a continuation turn. Compare that projection with the scenario
contract, not with provider-native wire formatting. A semantically equivalent
provider representation is valid; an omitted/rewritten tool, incompatible
choice policy, or missing S3 prior-result context is an adapter-interface defect.

| Condition | Status |
| --- | --- |
| Unsupported mode | `skipped` / `unsupported_mode` |
| Failed local preflight | `unavailable` for every eligible selected row |
| Expected S4 `WorkflowExecutionError` with its exact failure projection | evaluate the S4 invariant |
| Observed request rendering, translation, parse, normalization, or executor observation contradicts the common request/call contract | `adapter_error` / `adapter_interface` |
| Other caught operational exception | `adapter_error` |
| Completed execution with a failed positive invariant | `behavioral_mismatch` |
| Completed positive invariant | `passed` |

The total classifier receives preflight result, planned-row status, recorded
adapter observation, normalized calls, invocations/results, executor outcome,
and final-result projection. It records the furthest reached stage:
`preflight`, `request_render`, `transport`, `response_parse_normalize`,
`executor_tool_loop`, or `completion_assessment`. It must never raise for a
row-local operational outcome and must preserve `KeyboardInterrupt` and
`SystemExit`.

Every non-passed row also has `failure_locus`: `model_behavior` only when the
actual rendered request and normalized-call stream match the controlled
contract but the model does not satisfy its row invariant; `adapter_interface`
when rendering, request translation, parse, normalization, or executor
observation contradicts that contract, in which case status is `adapter_error`;
otherwise `indeterminate`. `behavioral_mismatch` is reserved for a correctly
observed adapter path that violates an S1--S5 behavioral invariant.

Continue after each row-local error or mismatch. Only target-wide preflight can
avoid execution. The reducer emits every status count, including zeroes. It
rejects duplicate scenario IDs and an empty selected set before preflight;
skipped-only runs are `unavailable`. For eligible rows, all passed means
`passed`; otherwise any adapter error means `adapter_error`; otherwise any
mismatch means `behavioral_mismatch`; otherwise `unavailable`.

### Bounded diagnostics

Use ordinary dictionaries plus standard-library UUID, UTC time, hashing, and
JSON. Format version 2 has mandatory target fields `run_id`, `timestamp`,
`target`, source-revision provenance, allowlisted non-secret configuration,
summary status, and all five zero-filled status counts. Source revision is an
optional validated `DAR_LIVE_MATRIX_SOURCE_REVISION` value or explicit
`unavailable`; the runner does not spawn a Git process to discover it. Every
live invocation includes `manual_authorization`: a digest of a constrained
opaque operator-supplied authorization identifier plus the digest of its
canonical target/model/configuration/mode/scenario/lifecycle scope. The
identifier accepts only 1--128 ASCII letters, digits, `.`, `_`, `:`, or `-`,
and is never retained raw. Fake or non-execution records use `not_applicable`.
The runner rejects a missing or invalid identifier during local preflight before
adapter/executor activity. It is provenance, not a substitute for the current
user/operator authorization. Every
row has `mode`, `scenario`, `status`, `reason`, `failure_locus`,
`stage`, `model_identifier`, artifact identity/provenance, adapter/backend/parser
version provenance, generation-settings provenance, actual rendered-tools digest,
tool-choice value/provenance, normalized calls, invocation/results, completion
class, and diagnostic references. Any unavailable value is explicit
`unavailable` or `not_applicable`, never omitted.

The recorder hashes canonical serialization of the observed first adapter-facing
tool declaration, not the fixture reconstruction. It hashes the controlled
prompt separately. A single bounded recursive serializer applies to every
model-derived or handler-derived value: normalized-call arguments, invocation
arguments/results, final text, error text, and diagnostics. It retains only
structure, scalar type, length, and digest for free-form string values; row
invariants compare raw values in memory before serialization. It removes values
under case-insensitive secret-like keys (`authorization`, `api_key`, `token`,
`secret`, `password`, `cookie`) and never emits arbitrary string previews.
The CLI drops `--api-key`; existing configured authentication remains the only
credential path. The receipt allowlists model id and sanitized base-URL origin,
and represents a local model path only by basename plus a digest of the original
unresolved path string. Base URLs must be HTTP(S), have no userinfo, query, or
fragment, and record only normalized scheme/host/optional-port origin. Path
preflight checks existence and readability without resolving symlinks or
recording an absolute path. The receipt never serializes API keys,
authorization headers, absolute paths, or raw responses.

### Positive invariants

- S1: one exact normalized and invoked `create_record` call, no extra call,
  `normal_text` completion.
- S2: one exact normalized and invoked valid `transform_record` call, no extra
  call, `normal_text` completion.
- S3: exact lookup then transform using returned `record-seed`, deterministic
  transformation, `normal_text` completion.
- S4: one failed `fail_controlled` call, `controlled_tool_failure` completion,
  and no continuation or other call.
- S5: zero normalized/invoked calls and `normal_text` completion whose final
  result is a non-empty, non-whitespace string.

`normal_text` is a completed `WorkflowResult` with a final string matching the
row rule. `controlled_tool_failure` is the expected package-owned
`WorkflowExecutionError`, one failed controlled result, and one recorded adapter
request. Any other exception, non-string S5 final result, malformed/dropped
normalized call, or unexpected continuation is classified by the total reducer.

The deterministic matrix remains the only authority for S2 invalid variants
and S6. The live runner must never prompt a model to emit malformed data.

## Delivery Slices (TDD)

1. **Selector, preflight, and eligibility.** Add RED tests in
   `tests/test_model_interface_matrix.py` for S1--S5 default/explicit selection,
   duplicate/empty selection rejection, Apple async-only handling, required
   configuration, and zero adapter/executor calls on failed preflight. Implement
   the selector, local-only preflight, and runner-local eligibility mapping.
2. **Observation, receipt, and continuation.** Add RED fake-adapter/executor
   tests proving the recording facade captures actual exposed tools, tool choice,
   per-turn message/result context, normalized calls, completion projections,
   source-revision provenance, and every required receipt field. Prove observed
   rendering/normalization defects become `adapter_interface`, ordinary model
   misses become `model_behavior`, and uncertain partial failures are
   `indeterminate`. Prove the canonical request projection accepts semantically
   equivalent provider shapes and rejects omitted/rewritten tools, incompatible
   tool choice, missing S3 result context, parse/normalization defects, and
   dropped calls as `adapter_error`.
   Prove every selected eligible row gets a result, a mismatch does not stop later
   rows, S4's expected failure passes only on its exact projection, target-wide
   preflight marks rows unavailable, and summary precedence/counts are deterministic.
   Implement the facade, total classifier, receipt builder, and reducer.
3. **Bounded serialization.** S1--S5 invariant evaluation is established in
   slice 2 before the total classifier. Add RED tests for actual-render hashes,
   recursive structure/digest projection, secret-like keys and arbitrary
   sensitive strings, missing provenance, sanitized URL/path configuration, and
   no credential serialization. Implement only those fields; do not introduce
   provider-specific capture abstractions.
4. **Manual evidence refresh.** Run one target at a time only after the current
   user/operator explicitly names target, model/configuration, modes, scenarios,
   and any local server lifecycle authorization. The environment opt-in alone is
   insufficient. Record non-secret authorization provenance and the classified
   receipt in `validation.md`. Apple S1 remains blocked by A2 B5.1.

## Validation

```sh
poetry run pytest tests/test_model_interface_matrix.py -q
poetry run pytest \
  tests/test_executor.py tests/test_openai_client.py \
  tests/test_litellm_provider_adapter.py tests/test_local_models.py \
  tests/test_mlx_models.py tests/test_apple_foundation_models.py -q
poetry run ruff check src tests
pre-commit run --files \
  tests/model_interface_matrix.py tests/test_model_interface_matrix.py \
  scripts/run_live_model_interface_matrix.py \
  specs/live-model-interface-acceptance/spec.md \
  specs/live-model-interface-acceptance/plan.md \
  specs/live-model-interface-acceptance/tasks.md \
  specs/live-model-interface-acceptance/validation.md
git diff --check
```

The second command verifies unchanged deterministic seams; it is not permission
to run a live provider. A later manual run requires
`DAR_RUN_LIVE_MODEL_INTERFACE_MATRIX=1` and one explicit target with its
required configuration. It must not run in pytest or CI.

## Risks and Deferred Decisions

- Local S1 misses are compatibility observations, not prescribed adapter fixes.
- Metadata availability varies by target; record absence instead of adding new
  provider APIs or runtime introspection.
- Repeat-rate scoring, persistence, and cross-run aggregation are deferred until
  the first complete receipts demonstrate their value.
