# Live Model-Interface Acceptance Tasks

Status: T1--T5.1 complete; T5.2 compatibility resolution pending

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
- [x] T4.2 [manual gate] With an explicit current authorization and
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

## T5 — vLLM Endpoint Compatibility Follow-up

- [x] T5.1 [manual diagnosis] Characterize the Qwen3 vLLM endpoint's
      parser/template behavior for the recorded S1 mismatch before proposing a
      DAR implementation change.
  - Evidence: the authorized 2026-08-30 S1 sync and async receipts each show
    two valid `create_record` calls followed by no text completion for
    `mlx-community/Qwen3-4B-Instruct-2507-nvfp4` at revision
    `111ab717db337468c86004a79bd9df19c6e3986d`, served by vLLM Metal 0.28.0
    with `qwen3_xml`.
  - Candidate set: test exactly B0--B2 against the pinned artifact and vLLM
    0.28.0. B0 is the observed baseline: `qwen3_xml`, auto tool choice,
    tokenizer-provided template, automatic content-format detection, and the
    model's effective generation defaults. B1 is B0 with only
    `--chat-template-content-format string`; B2 is B0 with only
    `--chat-template-content-format openai`. Freeze all other settings. This
    is the complete task-authorized set; a parser, template, or generation
    change needs a new task and current authorization. The candidate options
    come from vLLM 0.28.0's documented CLI arguments, not inferred parser
    substitutions.
  - Procedure: with explicit current authorization, start and stop a temporary
    server for each candidate in a temporary Herdr workspace; do not modify
    the installed launchd configuration. For each candidate, first run one
    direct OpenAI-compatible `/v1/chat/completions` S1 control with the same
    fixed model, messages, tool schema, tool choice, and post-tool-result
    continuation as the runner scenario. Then run the bounded DAR S1 sync and
    async probes. Retain format-version-2 redacted receipts for DAR and only a
    bounded structural projection for the direct control: request/configuration
    digest, returned tool-call count/names/argument-validity, and final-text
    presence. Record non-secret provenance for vLLM version, model revision,
    candidate ID and one-variable delta, parser, template source plus digest,
    detected content format, frozen generation settings, and the documentation
    version/source in `validation.md`. Give the DAR endpoint runner an HTTP(S)
    base URL ending in `/v1`; it adds the chat-completions suffix itself.
  - Attribution: if the direct control and DAR have the same invalid S1 shape,
    attribute the observation to the tested endpoint/model configuration. If
    the direct control meets S1 but DAR does not, record an adapter discrepancy
    and create a separate test-first adapter task. If the direct control cannot
    make the bounded request, record that candidate as unavailable; do not
    substitute a different request or configuration.
  - Acceptance: either record one B0--B2 configuration that produces one
    schema-valid `create_record` call and a final text completion in both DAR
    modes, or record the candidate-specific result for every B0--B2 probe.
    A negative conclusion is limited to B0--B2, vLLM 0.28.0, and the pinned
    model revision. Do not change a DAR adapter merely to force a tool call;
    any adapter remedy needs the separate task justified by the paired evidence.
  - Boundary: no pytest/CI live dependency, model download, external tool
    dispatch, credentials, or unredacted provider capture. This task does not
    authorize a durable package or launchd configuration change, a new
    provider-specific capture interface, or additional candidates.

- [ ] T5.2 [manual compatibility resolution] Address the model/parser behavior
      mismatch only after T5.1 records its configuration-specific evidence.
  - Prerequisite: T5.1 identifies either one configuration that satisfies S1
    in sync and async mode, or a reproducible failure for its tested
    configuration set.
  - Procedure: if T5.1 identifies a passing configuration, record its exact
    non-secret provenance as the endpoint target's supported manual-test
    configuration and repeat the bounded S1 sync/async confirmation. If it
    does not, record the model/parser combination as unsupported for this
    acceptance target and retain the receipt references. If the evidence shows
    DAR diverges from an otherwise conforming endpoint response, create a new
    test-first DAR adapter task that names the affected adapter boundary and
    its focused regression tests; do not implement that change under T5.2.
  - Acceptance: `validation.md` records one of those three evidence-backed
    outcomes. It makes no general compatibility claim beyond the exact model
    revision, vLLM version, parser/template configuration, and S1 modes tested.
  - Boundary: no speculative parser substitution, durable launchd/package
    configuration change, model download, or DAR adapter modification. Any
    source change requires its separately authorized task.

## Consistency Check

- T1 maps to plan “Selection and eligibility” and spec acceptance requirements
  1--2.
- T2 maps to plan “Row execution and receipt” and spec acceptance requirements
  1--3.
- T3 maps to plan “Bounded diagnostics” and spec acceptance requirements 3--4;
  positive-invariant evaluation is deliberately established in T2 before its
  classifier is implemented.
- T4 maps to plan “Validation” and the spec's manual-gate boundary.
- T5 maps to the plan's unresolved affected-target rerun checklist and remains
  manual evidence, not deterministic matrix coverage. T5.2 consumes T5.1's
  evidence rather than presuming a model, parser, or DAR adapter cause.
