# macOS Generalized MLX Embedding Execution Validation

Status: generic ABI/provider and one sealed workflow package validated; exact
matrix admission recorded; MLE7 and MLE8 expansions planned

## Completed Generic Evidence

- MLE0--MLE5 established generic descriptor, material, provider, and Darwin
  synthetic-conformance behavior without a named production embedding model.
- The elevated Darwin/arm64 synthetic competency receipt uses `mlx==0.32.2` and
  proves the installed ABI math, not acceptance of a workflow-owned material
  closure.

## MLE6 Traceability

| Gate | Required evidence | Status |
| --- | --- | --- |
| Material decision | approved package-local v2 lock and ABI descriptor | complete; MLE6.2 fixture package |
| Fixture conformance | trusted local reference vectors bound to that lock | complete; MLE6.3 local-only reference fixture |
| Offline admission | fake-only package/provider/index regressions | complete; MLE6.4 fake provider/index coverage |
| Darwin competency | authorized redacted package-bound MLX receipt | complete; v3 package `mle6.5-receipt.json`, 3×384 vectors, `max_abs_error` `0.00022599101066589355` |
| Matrix admission | exact package/material support row | complete; package-local `support-matrix-row.json` and non-transferability tests |

## Boundaries

- The approval record at `tests/fixtures/mlx-gte-tiny/mle6-approval.md` selects
  one cached BERT-compatible closure for local internal conformance only. It
  does not convert the legacy v1 fixture into an MLE6 package or independently
  authorize a competency run.
- This MLE6 goal explicitly authorized local cache material verification,
  local-only reference-vector generation, and the Darwin competency run. The
  committed receipt retains only redacted package identity, limits, resource,
  dimension, opaque-output, and pass/fail evidence.
- MLE7 and MLE8 have no package, material, fixture, or Darwin evidence yet.
  Their planned model names do not establish support, authorize a download or
  material use, or transfer the MLE6 receipt to either tokenizer/executor ABI.
