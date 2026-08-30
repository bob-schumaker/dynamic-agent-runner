# Live Model-Interface Acceptance Tasks

Status: implementation-ready; execute T1 through T4 in order

## Authority and Route

- Governing spec: `spec.md`
- Implementation plan: `plan.md`
- Delivery target: `/Users/roschuma/Repos/roschuma/dynamic-agent-runner`
- Route: test-first changes in the existing test corpus and manual runner;
  no package module, provider-specific capture interface, or server lifecycle
  implementation is authorized.

## T1 — Positive Selection and Local Preflight

- [x] T1.1 [tests/RED] Add focused tests in
      `tests/test_model_interface_matrix.py` for S1--S5 default selection,
      explicit positive selection, negative/duplicate/empty selection rejection,
      Apple async-only planning with one skipped row per selected scenario, and
      local preflight failures. Cover endpoint URL rejection for unsupported
      schemes, userinfo, query, and fragments before adapter construction.
      Cover missing and unsafe `--authorization-reference` values (including
      secret-like text and URLs) rejected before adapter construction.
      Prove failed preflight calls neither adapter construction nor workflow
      execution.
  - Acceptance: all selected rows are planned in deterministic order with an
    explicit per-scenario `skipped` unsupported-mode row; no provider action
    occurs.
  - Validation: `poetry run pytest tests/test_model_interface_matrix.py -q`
- [x] T1.2 [implementation/GREEN] Update
      `tests/model_interface_matrix.py` and
      `scripts/run_live_model_interface_matrix.py` with the smallest
      live-positive selector, runner-local eligibility mapping, and local-only
      preflight needed by T1.1.
  - Acceptance: the full S1--S6 deterministic catalog is unchanged; the manual
    runner accepts only S1--S5, rejects unsafe endpoint URLs and invalid opaque
    authorization identifiers during preflight, and no longer exposes `--api-key`.
  - Validation: `poetry run pytest tests/test_model_interface_matrix.py -q`

## T2 — Observation, Classification, and Receipt

- [x] T2.1 [tests/RED] Add fake adapter/executor tests that expose the actual
      adapter-facing tool declaration/tool-choice policy and normalized calls.
      Cover row continuation after mismatch/error, target-wide unavailable rows,
      every summary precedence branch, zero-filled status counts, and
      preservation of `KeyboardInterrupt`/`SystemExit`.
      Include per-turn request/result-context mapping, source-revision
      provenance, digest-only `manual_authorization`/`not_applicable` provenance,
      canonical target/model/configuration/mode/scenario/lifecycle scope binding,
      receipt schema matrix, and `model_behavior`,
      `adapter_interface`, and `indeterminate` attribution cases. Add canonical
      common-request projection cases for equivalent provider shapes,
      omitted/rewritten tools, incompatible choice policy, and missing S3
      result context; all rendering/translation/parse/normalization/observation
      defects must be `adapter_error` with `adapter_interface`.
      Include RED scenario-invariant evaluator cases for all S1--S5 before the
      total classifier is implemented.
  - Acceptance: a row-local outcome cannot raise out of the runner or suppress
    a later selected row.
  - Validation: `poetry run pytest tests/test_model_interface_matrix.py -q`
- [x] T2.2 [implementation/GREEN] Add script-local recording facade, planned
      row builder, total classifier, receipt builder, and summary reducer in
      `scripts/run_live_model_interface_matrix.py`.
  - Acceptance: receipt format version 2 has all required target/row fields
    from plan “Bounded diagnostics,” including zero-valued status counts and
    source-revision and manual-authorization provenance, with explicit absence
    provenance; it does not retain raw provider responses.
  - Validation: `poetry run pytest tests/test_model_interface_matrix.py -q`

## T3 — Safe Diagnostics

- [x] T3.1 [tests/RED] Add adversarial fake receipt values for arbitrary strings,
      secret-like keys, unsafe authorization references, nested arguments/results,
      exception text, URL userinfo,
      query/fragment, unsupported URL schemes, and symlinked local-model paths.
  - Acceptance: raw free-form strings never enter a receipt; URL/path metadata
    follows the plan's explicit sanitization and unresolved-path rules.
  - Validation: `poetry run pytest tests/test_model_interface_matrix.py -q`
- [x] T3.2 [implementation/GREEN] Implement actual-render and prompt digests,
      bounded recursive serialization, secret-key redaction, sanitized base-URL
      origin, and local-model basename-plus-digest representation.
  - Acceptance: no receipt path serializes an API key, authorization header,
    absolute local-model path, raw authorization identifier, unbounded text, or
    raw provider response.
  - Validation: `poetry run pytest tests/test_model_interface_matrix.py -q`

## T4 — Regression and Manual Acceptance Evidence

- [x] T4.1 [validation] Run the focused matrix suite, affected deterministic
      parity modules, Ruff, pre-commit, and `git diff --check` using the exact
      commands in `plan.md`.
  - Acceptance: all automated checks pass without live provider, model download,
    server, or external tool activity.
- [ ] T4.2 [manual gate] With an explicit current authorization and
      `DAR_RUN_LIVE_MODEL_INTERFACE_MATRIX=1`, run one configured target at a
      time. The authorization must name target, model/configuration, modes,
      scenarios, and any local-server lifecycle. The operator owns server
      lifecycle. Supply a constrained `--authorization-reference` opaque
      identifier that records only its digest and the scope digest without
      credentials. Record non-secret authorization
      provenance and each classified receipt in `validation.md`; do not run
      Apple S1 until A2 B5.1 is resolved.
  - Acceptance: the receipt follows format version 2 and is retained without
    secret-bearing raw transport data.

## Consistency Check

- T1 maps to plan “Selection and eligibility” and spec acceptance requirements
  1--2.
- T2 maps to plan “Row execution and receipt” and spec acceptance requirements
  1--3.
- T3 maps to plan “Bounded diagnostics” and spec acceptance requirements 3--4;
  positive-invariant evaluation is deliberately established in T2 before its
  classifier is implemented.
- T4 maps to plan “Validation” and the spec's manual-gate boundary.
