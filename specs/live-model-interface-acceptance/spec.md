# Live Model-Interface Acceptance Specification

## Metadata

- Feature slug: `live-model-interface-acceptance`
- Mode: `guided`
- Artifact type: manually gated acceptance contract
- Status: manual acceptance evidence recorded
- Owner: `specs/model-interface-parity/spec.md`
- Related specs:
  - `specs/model-interface-parity/spec.md`
  - `specs/mlx-local-model-tool-use/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/apple-foundation-model-adapter/spec.md`
- Evidence: `validation.md`
- Implementation plan: `plan.md`

## Objective

Make the optional live matrix an honest compatibility acceptance gate. It must
measure whether a real model and its selected adapter complete safe, positive
tool-use behavior, while leaving malformed and adversarial provider payloads to
the deterministic injected-seam matrix that can reproduce them reliably.

## Scope and Contract

The existing `model-interface-parity` deterministic matrix remains the
contract authority for S1--S6, including S2 invalid-argument variants and S6
malformed provider output. Those rows are not live-model pass criteria: a
well-behaved model commonly repairs, declines, or paraphrases an instruction to
emit malformed data rather than emitting the test fixture's exact bad payload.

The manually gated live matrix must accept only these behavioral scenario IDs:

| Row | Required live observation |
| --- | --- |
| S1 | exactly one schema-valid `create_record` call and the expected controlled result path |
| S2 | exactly one schema-valid `transform_record` call with `record-seed` and `uppercase` |
| S3 | ordered `lookup_record` then `transform_record` continuation |
| S4 | exactly one `fail_controlled` call, typed controlled failure, and no continuation or other call |
| S5 | a valid non-empty final text response with no controlled invocation |

S1 and S2 must have no extra invocation. S3 must call
`lookup_record({"key": "seed"})`, pass its returned `record-seed` identifier to
`transform_record`, make no other call, and complete with the deterministic
transformation. The live runner uses the parent parity specification's
normalized-call, invocation, and completion observables; it does not compare
response prose except S5's bounded completion check.

S2 invalid, wrong-type, invalid-enum, unknown, malformed, and S6 remain
deterministic replay/injection rows. A live run may report them as diagnostics,
but it must never fail merely because a model refuses to produce the requested
invalid payload.

The runner remains manually enabled by
`DAR_RUN_LIVE_MODEL_INTERFACE_MATRIX=1`, requires an explicit target plus its
target-required configuration, and exposes only in-memory controlled handlers.
It does not start, stop, download, or mutate external resources. An operator
controls any local server lifecycle separately, including through a temporary
Herdr workspace where desired.

| Target | Eligible modes | Required configuration |
| --- | --- | --- |
| `apple` | async | eligible system model; fixed Apple alias, no `--model` |
| `codex`, `openai`, `litellm` | sync, async | `--model` plus the target's configured provider authentication |
| `endpoint` | sync, async | `--model` and `--base-url` |
| `llama_cpp` | sync, async | `--model`, `--model-path` |
| `mlx_qwen3` | sync, async | `--model`, `--model-path` |

An unsupported target/mode is not a behavioral mismatch. The selector must
reject any scenario ID other than `S1`, `S2`, `S3`, `S4`, and `S5` before it
makes a provider request.

## Acceptance Requirements

1. Each requested `(target, eligible mode, scenario)` produces one row result:
   `passed`, `behavioral_mismatch`, `adapter_error`, `unavailable`, or
   `skipped`. A row is `behavioral_mismatch` only when DAR completed the
   provider interaction but the positive-row contract did not hold;
   `adapter_error` is a package/provider error at or before normalization;
`unavailable` is a failed target preflight; and `skipped` records an
unsupported mode with a stable reason. A target-wide preflight failure
records every eligible selected row as `unavailable`. An unsupported mode
records one `skipped` row for each selected scenario, so every receipt row
retains a target, mode, and scenario identity.
2. A target summary contains counts for every row status and is `passed` only
   when every eligible attempted row passed; otherwise it is `adapter_error`
   if any row has that status, `behavioral_mismatch` if any row has that status,
   or `unavailable` when no eligible row was attempted. A row-local failure
   must not prevent later selected rows from receiving a result; only target
   preflight may short-circuit the target.
3. The receipt is versioned and records a run identifier and timestamp, source
   revision when available, non-secret target configuration, target/mode/scenario,
   row status and reason, model identifier, artifact identity or explicit
   `unavailable`/`not_applicable`, adapter/backend/parser version, generation
settings, normalized calls, invocation sequence, completion class, and
   bounded diagnostic references. A live invocation also records a bounded
   `manual_authorization` provenance object; it retains only digests of a
   constrained opaque authorization identifier and canonical execution scope,
   never the supplied identifier itself. Non-execution/fake records use explicit
   `not_applicable`. Its focused fake tests own the schema and
   aggregation rules in `tests/test_model_interface_matrix.py`; the runner is
   `scripts/run_live_model_interface_matrix.py`.
4. A behavioral-mismatch row includes bounded, redacted prompt and tool-render
   digests plus parser and sampling settings. It may include a bounded redacted
   provider-shape diagnostic. Receipts never retain API keys, authorization
   headers, or secret-bearing raw transport data. Full raw captures, if needed,
   remain an operator-local artifact outside the receipt and are referenced only
   by a digest or explicit `unavailable`/`not_applicable` provenance.
5. One attempt per selected row is sufficient for this first manual gate. The
   receipt records that attempt; no rate threshold or multi-run score is
   inferred until completed receipts demonstrate a need.
6. Unit tests for any runner or receipt changes remain fake-backed and offline.
   A live result is manual evidence only and does not enter ordinary pytest or
   CI.

## Initial Work Checklist

- [x] Update `tests/model_interface_matrix.py` and
      `tests/test_model_interface_matrix.py` with a positive-only selector,
      target/mode eligibility, and fake RED coverage for row classification,
      continuation, and target aggregation. Negative injected rows must remain
      deterministic.
- [x] Update `scripts/run_live_model_interface_matrix.py` to collect all
      selected eligible rows and emit the versioned classified receipt.
- [x] Add common bounded/redacted provenance and diagnostic references to that
      receipt; do not add target-specific diagnostic abstractions unless the
      common fields prove insufficient.
- [ ] Re-run affected targets with their resolved configuration and classify
      remaining mismatches from the receipt evidence.

## Out of Scope

- Changing a provider adapter merely to force one model artifact to make a tool
  call.
- Treating identical prose, token ids, latency, or tool-call ids as parity.
- Automated server lifecycle, model downloads, external tool use, approval
  interaction, or external mutations.
- Replacing deterministic malformed-payload coverage with live prompting.

## Consistency Decision

This is one acceptance-contract follow-up owned by the existing parity feature,
not a replacement for its delivered deterministic matrix. The Apple SDK bridge
construction failure is an independent concrete regression and is tracked in
`specs/apple-foundation-model-adapter/a2-tasks.md`.

## Inline Validation Checklist

- [x] The contract keeps all malformed and adversarial provider rows under the
      deterministic matrix.
- [x] The positive live rows map directly to S1, S2, S3, S4, and S5 in
      `model-interface-parity`.
- [x] Initial results are retained as observations in `validation.md`, with no
      claim that a local-model behavioral mismatch is an implementation defect.
