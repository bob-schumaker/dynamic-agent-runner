# Workflow Model Support Matrix Tasks

Status: WMS1--WMS5 are complete. WMS5 repaired the registered Fastmail probe
identity, reconciled its profile-bound pinned MCP review and legacy registration,
and recorded one redacted live read-only receipt.

## Prerequisites

- Spec: `spec.md`
- Plan: `plan.md`
- Existing inputs: `../model-interface-parity/`, `../fastmail-inbox-triage/`,
  `../workflow-embedding-index-artifacts/`, and model-material/capability
  contracts.

## Task List

- [x] WMS1.1 [discovery/tests, RED] Inspect the existing capability-report,
      package-lock, and live-matrix types; add focused failing tests for a
      profile/cell classifier without changing existing S1--S6 semantics.
  - Spec: FR-001, FR-002, AC-001, AC-002, WMS1 Classifier Contract.
  - Files/components: `src/dynamic_agent_runner/` capability and material
    boundaries; `tests/test_workflow_model_support_matrix.py`.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py -q`.
  - Evidence: the new focused suite fails at collection before implementation;
    it fixes the canonical profile/material facts and all four status outcomes
    without importing an adapter, provider, or runtime.

- [x] WMS1.2 [implementation, GREEN] Implement validated declarative support
      profiles and pure cell classification with stable reasons for supported,
      not-applicable, blocked, and deferred states.
  - Spec: FR-001, FR-002, NFR-002, NFR-003, WMS1 Classifier Contract.
  - Depends on: WMS1.1.
  - Evidence: fake facts prove no model load, download, provider invocation, or
    tool dispatch occurs during classification.
  - Boundary: one internal classifier module and its tests only; do not add a
    runner, script, live entry point, or broad public export in WMS1.
  - Evidence: `workflow_support_matrix.py` accepts only immutable profile and
    candidate facts, canonicalizes profile digests, and produces the closed
    terminal status/reason set without importing a runtime collaborator.

- [x] WMS1.3 [tests, RED/GREEN] Add package/material identity binding tests,
      including rejection of a receipt whose profile/package/material digest
      differs from the evaluated cell.
  - Spec: FR-006, AC-005, WMS1 Classifier Contract.
  - Files/components: classifier/receipt boundary and
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS1.2.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py -q`.
  - Evidence: focused receipt-transfer tests were RED before the receipt data
    contract and pure evaluator existed, then GREEN with exact profile, adapter,
    material, test-mode, status, and reason binding checks.

- [x] WMS2.0 [tests, RED/GREEN] Extend the pure receipt contract for every
      deterministic WMS2 result before adding profile-specific execution.
  - Spec: FR-005, NFR-001, NFR-003.
  - Files/components: `workflow_support_matrix.py`,
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS1.3.
  - RED: require a non-negative `dispatch_count` and retain only stable
    classification reasons as bounded diagnostics. A non-supported classified
    cell cannot record a nonzero dispatch count; profile tests must be able to
    prove one exact synthetic dispatch or zero dispatch before execution.
  - GREEN: retain no model input/output, tool result, mailbox content, prompt,
    credential, path, or host detail in the receipt representation. Update the
    existing pure receipt-binding vectors rather than adding a renderer or a
    second receipt type.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py -q`.

- [x] WMS2.1 [tests, RED] Define a synthetic Fastmail support profile using
      only de-identified fixture messages and a controlled read-only
      `search_email` handler; demonstrate that the profile cannot touch MCP,
      OAuth, network, or mailbox state.
  - Spec: FR-003, AC-003.
  - Files/components: de-identified Fastmail shape fixture and current
    Fastmail binding/terminal-report seams,
    `tests/test_dar_authoring_mcp_tools.py`,
    `tests/test_dar_authoring_runner.py`, and
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS2.0.
  - RED: add one test-owned, de-secreted identity fixture for the registered
    v4 package digest, pinned Qwen artifact hash/configuration fingerprint, and
    reviewed read-only surface digest. Derive the profile material identity
    from that fixture; do not treat prose-only historical acceptance evidence
    as a reusable material lock.
  - RED: define `fastmail-triage-synthetic-v1` as synthetic-only, requiring
    tool use plus the exact read-only `search_email` surface. A missing tool
    path is `not_applicable`; stale or mismatched package/surface identity is a
    zero-dispatch blocked row.
  - Boundary: install fail-on-call MCP/OAuth/network sentries. The fixture
    handler accepts only `{}`, returns de-identified bounded data, and the
    classifier runs before any fake model or tool construction.

- [x] WMS2.2 [implementation, GREEN] Integrate the synthetic Fastmail fixture
      with eligible adapters through the existing coordinator/host test seams,
      retaining exact dispatch-count and contract-valid report assertions.
  - Spec: FR-003, FR-007.
  - Depends on: WMS2.1.
  - GREEN: reuse the existing fake Fastmail binding and deterministic adapter
    path to require exactly one `search_email({})` dispatch, zero mutation,
    and a terminal `FastmailTriageReport`-valid result. Record a synthetic
    receipt with `dispatch_count == 1`; stale, unsupported, and denied rows
    remain zero-dispatch.
  - Validation: `poetry run pytest
    tests/test_workflow_model_support_matrix.py
    tests/test_dar_authoring_mcp_tools.py
    tests/test_dar_authoring_runner.py
    tests/test_fastmail_triage_report.py -q`.

- [x] WMS2.3 [tests, RED/GREEN] Define and execute the distinct synthetic
      `embedding-index-synthetic-mle6-v1` sealed-embedding profile against an
      injected provider; cover missing ABI, wrong material role, and an
      unonboarded embedding package as classified non-executing rows.
  - Spec: FR-002, FR-003, AC-002.
  - Files/components: existing MLE6 package and fake embedding/index test
    seam, `tests/test_workflow_model_support_matrix.py`,
    `tests/test_mlx_gte_tiny_mle6_execution.py`, and the pure receipt boundary.
  - Depends on: WMS2.0.
  - RED: parse the existing sealed MLE6 package lock, execution descriptor,
    and capability requirements from test fixtures; derive the profile's exact
    package ID, material-lock digest, `tokenizer`/`weights` roles,
    execution-descriptor digest, `embedding.execute.v1` capability identity,
    and ABI identity. Do not duplicate those identities as literals. The
    synthetic profile has no host/MPS requirement and is distinct from the
    package's `embedding-index-sealed-v1` Darwin competency row.
  - RED: use the WMS2.0 pure receipt contract for a supported synthetic result
    with one dispatch and each non-executing row with zero dispatches.
  - GREEN: run exactly one bounded synthetic input through the existing
    `EmbeddingExecutionService` using its injected deterministic fake provider
    and the binding derived from that same lock, descriptor, and capability
    requirement. Assert the supported profile/candidate cell, one provider
    dispatch, and no model import, model download, network, mailbox, OAuth,
    or MPS access.
  - GREEN: use the same profile for three zero-dispatch rows: an absent exact
    ABI capability is `blocked/required_abi_unavailable`; an otherwise matching
    identity missing `tokenizer` is `blocked/required_material_missing`; and a
    different package identity is `blocked/material_identity_mismatch`. These
    rows must not call the injected provider and cannot inherit the package's
    Darwin competency receipt or supported row.
  - Review disposition (2026-09-13): Council required the distinct synthetic
    profile identity, fixture-derived facts, explicit dispatch receipts, and
    the sealed MLE6 execution test in the validation command. Ponytail accepted
    reuse of the existing fake provider and package fixture; no new runtime
    registry, provider adapter, model fixture, or dependency is warranted.
  - Validation: `poetry run pytest
    tests/test_workflow_model_support_matrix.py
    tests/test_mlx_gte_tiny_mle6_execution.py
    tests/test_embedding_execution.py
    -q`.

- [x] WMS2.4 [tests, RED/GREEN] Define the floorplan SVG profile from the exact
      sealed converter, model-material, generation-budget, MPS-policy, and
      output-validator facts. Add deterministic non-executing classification
      vectors for every missing or mismatched fact.
  - Spec: FR-008, FR-009, AC-006.
  - Files/components: floorplan fixture/material tests and
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS2.0.
  - RED: derive a synthetic fixture profile and a separate
    `floorplan-svg-mps-completion-v1` live profile from the sealed floorplan
    package. Bind package/material lock, execution descriptor, converter asset,
    generation budget (through the descriptor), and terminal SVG validator
    digests. The synthetic profile has no MPS requirement; the live profile
    requires the declared MPS host policy and authorization, but does not run
    MPS in pytest.
  - GREEN: run the existing admitted JSON-to-SVG converter/validator fixture
    only after the synthetic cell is supported. Cover zero-execution rows for
    absent/mismatched material, converter, descriptor/budget, validator,
    runner, MPS policy, and authorization facts. The MPS completion row and its
    receipt remain WMS3.3 work.
  - Execution note: the existing fixture invokes macOS `sandbox-exec`; when
    nested sandbox policy rejects it, run this focused deterministic test
    outside the Codex sandbox. That is neither an MPS probe nor authorization
    for a model run.
  - Validation: `poetry run pytest tests/test_floorplan_svg_fixture.py
    tests/test_workflow_model_support_matrix.py -q`.

- [x] WMS2.5 [tests, RED/GREEN] Add a controlled structured-output-after-tool-
      use profile with schema-valid success and pre-dispatch
      `not_applicable` coverage for adapters without the declared capability.
  - Spec: FR-008, FR-010, AC-007.
  - Files/components: `tests/test_workflow_model_support_matrix.py`, existing
    model-interface matrix fixtures.
  - Depends on: WMS2.0.
  - RED: build one controlled two-turn fixture—not a pairing of unrelated S3
    and S5 tests—in which the adapter performs the declared harmless tool call
    and then returns a locally validated fixed JSON result schema. A missing
    `structured_output` adapter capability is `not_applicable` before adapter
    construction or tool dispatch.
  - GREEN: assert the exact tool dispatch sequence, schema-valid terminal JSON,
    one dispatch receipt, and no remote model/client access. Reuse the existing
    in-memory registry and deterministic adapter recorder; do not add a schema
    subsystem or provider special case.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py
    tests/test_model_interface_matrix.py -q`.

- [x] WMS2.6 [tests, RED/GREEN] Add a stateful-context profile with bounded
      prior turns, session restoration, selected-context assertions, and an
      overflow-retry classification fixture. Prove raw turns are absent from
      the resulting matrix receipt.
  - Spec: FR-008, FR-010, AC-008.
  - Files/components: `tests/test_workflow_model_support_matrix.py`, session
    and context-management test seams.
  - Depends on: WMS2.0.
  - RED: bind one profile to the existing fake session restoration and one-shot
    overflow-retry/compaction seam. Require the selected-context counts and
    retry terminal classification, rather than raw turns or provider payloads.
  - GREEN: prove the receipt stores only profile/cell facts, stable reason
    codes, and dispatch count; sentinel turns, summaries, and provider-window
    identifiers must be absent from its representation. No external model or
    compactor is allowed.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py
    tests/test_agent_sessions.py tests/test_executor.py -q`.

- [x] WMS2.7 [tests, RED/GREEN] Add a tool-pack-composition profile using
      injected web, workspace, and subagent collaborators. Prove descriptor
      selection, approval, dispatch, redaction, and external-I/O/process
      blocking without starting a child or external client.
  - Spec: FR-008, FR-010, AC-009.
  - Files/components: `tests/test_workflow_model_support_matrix.py` and
    existing web, workspace, subagent, and authorization test seams.
  - Depends on: WMS2.0.
  - RED: make one integrated controlled profile with injected fake web clients,
    workspace store, and subagent runner. It must exercise descriptor selection
    and approval before dispatch; existing isolated tool-pack unit tests alone
    are not matrix evidence.
  - GREEN: assert the exact selected descriptors, approval decision, bounded
    result shaping/redaction, and one dispatch count for each admitted
    collaborator. Install fail-on-call external-client and child-process
    sentries; the fake subagent runner is the only permitted collaborator.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py
    tests/test_registry.py tests/test_subagents.py
    tests/test_dar_authoring_authorized_tools.py -q`.

## WMS2 Readiness Review (2026-09-13)

- Council: the architecture triad (Aristotle, Ada, Feynman), run as a
  reduced-independence sequential review, required a shared execution-receipt
  prerequisite; fixture-derived identities; separate synthetic, live, and
  Darwin/MPS evidence; and integrated tests where the workflow contract crosses
  existing unit-test seams.

- Ponytail: reuse the existing fake Fastmail binding, MLE6 package execution,
  floorplan fixture, in-memory tool registry, fake session/compaction adapter,
  and fake web/workspace/subagent collaborators. Do not add a profile registry,
  model fixture, adapter, provider, schema framework, or new dependency.

- Verdict: WMS2.0--WMS2.7 are implementation-ready in dependency order. The
  only host-specific test condition is the existing floorplan fixture's nested
  `sandbox-exec` limitation recorded above.

- [x] WMS3.1 [tests, RED] Add a fake-only authorization and redaction contract
      for a Fastmail live candidate: no authorization, non-supported cell, or
      stale surface rejects before model construction or dispatch.
  - Spec: FR-004, FR-005, AC-004.
  - Files/components: live-matrix runner seam or a new narrow runner,
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS2.2.
  - Evidence (2026-09-13): offline probe tests prove a missing authorization,
    non-supported cell, or stale material identity prevents host opening and
    dispatch. The admitted test path performs exactly one injected dispatch and
    retains only fixed redacted receipt facts.

- [x] WMS3.2 [implementation, GREEN] Add the operator-gated read-only Fastmail
      entry point and fixed redacted receipt renderer. Keep it out of pytest and
      CI; require explicit target/profile plus authorization evidence.
  - Spec: FR-004, FR-005, NFR-001.
  - Depends on: WMS3.1.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py -q`.
  - Evidence (2026-09-13): `scripts/run_fastmail_support_probe.py` requires
    explicit environment opt-in, target, fixed live profile, authorization
    reference, exact support facts, and a package name matching the admitted
    material identity before it opens an already configured host. It invokes
    one registered saved workflow with no workspace files and writes only the
    fixed redacted receipt. The command is not a pytest or CI entry point.

- [x] WMS3.3 [tests, RED/GREEN + manual gate] Add the operator-gated floorplan
      completion route. It must require a `supported` descriptor-bound MPS cell,
      preserve resource-budget/reap evidence, validate the output stage selected
      by M9.3, and render only a redacted completion receipt.
  - Spec: FR-005, FR-009, AC-006.
  - Depends on: WMS2.4 and `../workflow-model-materials/tasks.md` M9.6, M10.3.
  - RED: add fake-only tests for a package-derived profile: missing opt-in or
    authorization, an unsupported MPS cell, a stale material/descriptor/
    converter/processor/validator digest, or a missing MPS policy must refuse
    before host opening or generation-worker creation. The supported fake path
    must prove exactly one dispatch, JSON admission, SVG rendering/validation,
    and a redacted receipt; no model, MPS, network, artifact download, or child
    process is permitted in pytest.
  - GREEN: add only a narrow floorplan probe and operator script. Derive the
    registered package revision and compiled policy facts internally; do not
    accept a support-facts file. Extend the generic worker result only with a
    scalar `worker_reaped` attestation after controller-confirmed cleanup.
  - Receipt: fixed v1 redacted fields are profile ID/digest, adapter ID,
    material identity, test mode/status/reasons, dispatch count, target and
    authorization-reference digests, execution-descriptor digest,
    packed-context/generated-token/output-byte scalars, and `worker_reaped`.
    It must omit model JSON, SVG, image/prompt bytes, paths, process IDs, and
    worker handles.
  - Manual gate: after fake checks are green, explicit authorization permits
    one exact MPS profile/package/material cell. The run must admit model JSON,
    render SVG, validate SVG, and record the fixed receipt only after confirmed
    worker reap.
  - Validation: focused fake authorization/receipt tests, then a later explicit
    MPS authorization for one exact profile/package/material cell.
  - Review disposition (2026-09-13): Council architecture triad, run as a
    reduced-independence sequential deliberation, required package-derived
    identity, a closed redacted receipt, and separate model-JSON/SVG terminal
    assertions. Ponytail accepted one narrow probe/script and one generic
    cleanup scalar; it rejected a shared probe framework, operator-supplied
    support facts, and any floorplan-named host path. The task is
    implementation-ready; its explicit MPS authorization remains a later
    manual gate.
  - Implementation evidence (2026-09-13): the package-derived profile, generic
    worker-reap diagnostic scalar, opt-in operator command, and fixed redacted
    receipt are implemented. Offline coverage proves pre-inspection opt-in
    refusal, package-derived sealed identity, zero-dispatch invalid cells, and
    redacted successful evidence. `poetry run pytest -q
    tests/test_workflow_model_support_matrix.py tests/test_floorplan_svg_fixture.py
    tests/test_floorplan_mps_completion_probe.py
    tests/test_floorplan_mps_completion_probe_script.py
    tests/test_generation_worker.py tests/test_transformers_peft_model.py
    tests/test_dar_authoring_profiles.py tests/test_local_model_preparation.py`
    passed with 170 tests; `poetry run ruff check src tests scripts` passed.
  - Manual-gate evidence (2026-09-13): one explicitly authorized live MPS run
    for `floorplan-svg-mps-completion-v1` completed with status `supported`,
    dispatch count 1, packed context 2,223 tokens, generated 1,282 tokens,
    output 3,057 bytes, and confirmed `worker_reaped: true`. Its closed v1
    receipt binds profile digest
    `184d33c4b0a320a2bb7022b1ca80a1b86daa3203ea39d8afe75ebf3407e5e093`,
    descriptor digest
    `a986d842bb8d555ad6b5cfbe774a25a26db9eca34cd046d43a5158f9234526cb`,
    material-lock digest
    `79edaed8648cffb71972d0c8fcb3d18f100457d9cf46f0b58bc26fd16cc69cb8`,
    and authorization-reference digest
    `4519c2c2574ae800049fc79335a672f43c00803ee94884a0f0c83227ca7c9f07`.
    The probe admitted model JSON, rendered and validated SVG, and emitted no
    source image, prompt, model JSON, SVG, path, PID, or worker-handle data.

- [x] WMS4.1 [docs/validation] Publish the support-coverage report through the
      existing authored Sphinx documentation, defining all four statuses,
      package non-transferability, and per-run live authorization. Reconcile
      the matrix validation record with observed deterministic results and the
      existing authorized floorplan receipt; record that Fastmail has no live
      receipt. Do not add a runtime report generator.
  - Spec: FR-005, FR-007, NFR-003.
  - Files/components: `README.md`, `docs/files/validation-and-testing.rst`,
    `validation.md`.
  - Depends on: WMS3.3.
  - Report content: explain `supported`, `not_applicable`, `blocked`, and
    `deferred`; distinguish fixture, live, and unrecorded evidence; state that
    an exact profile/package/material/descriptor receipt cannot establish
    support for a different cell; identify WMS3.3's existing floorplan receipt
    without reproducing its source image, prompt, JSON, SVG, paths, or process
    data; and state that a future Fastmail run requires a new explicit
    authorization and redacted receipt.
  - Validation record: replace stale `not run` entries only where their named
    WMS task tests now prove the corresponding acceptance criterion; record
    each package-bound MLE6, MLE7, and MLE8 receipt as non-transferable. The
    manual register must contain the recorded floorplan receipt and explicit
    Fastmail absence, not an empty placeholder.
  - Boundary: use the existing documentation and validation artifacts; no
    runtime report API, profile registry, model/provider invocation, or new
    live run is in scope.
  - Validation: run the named focused matrix/profile suites, `poetry run pytest
    -q`, `poetry run ruff check src tests`, and `make -C docs html`; regenerate
    Sphinx source through the Makefile and do not hand-edit `docs/source/`.
  - Review disposition (2026-09-13): reduced-independence sequential Council
    architecture triad found the report, validation evidence, and manual
    receipt register are distinct artifacts and must not be conflated. It
    rejected stale empty-receipt language and unsupported MLX-row claims.
    Ponytail retained only the existing authored documentation and validation
    register, rejecting a runtime report generator or new reporting abstraction.
    WMS4.1 is implementation-ready with the reconciled scope above.
  - Evidence (2026-09-13): the README and authored Sphinx validation guide
    define all four statuses, exact-cell non-transferability, controlled
    fixture evidence, the recorded floorplan MPS receipt, and the absence of a
    Fastmail live receipt. `poetry run pytest -q` passed outside the nested
    sandbox with 2,603 passed, 1 skipped, and 7 deselected; the floorplan
    fixture's `sandbox-exec` and Darwin MPS tests require that host boundary.
    `poetry run ruff check src tests`, `make -C docs html`, `git diff --check`,
    and changed-file pre-commit passed.

## WMS5 — Fastmail Live-Probe Registration Identity Repair

- [x] WMS5.1 [tests, RED] Reproduce the owner-host registration shape in the
      Fastmail probe tests and prove that the probe admits only host-derived
      identity facts before opening a host or dispatching.
  - Spec: FR-004, FR-005, FR-011, AC-010.
  - Files/components: `tests/test_fastmail_support_probe_script.py`,
    `tests/test_fastmail_live_probe.py`,
    `scripts/run_fastmail_support_probe.py`, and the existing saved-workflow
    inspection and host-invocation seams.
  - Depends on: WMS3.2.
  - RED: use a de-secreted fixture whose registered workflow ID is
    `fastmail-inbox-triage-qwen-v4` and sealed package ID is
    `fastmail-inbox-triage-qwen`. Prove that this distinct pair can be admitted
    only when the script receives the workflow ID and derives the package,
    material, policy, and profile facts through registered state.
  - RED: prove an unknown workflow or stale derived material/policy fact refuses
    before host opening. Prove a stale reviewed surface is rejected by the
    configured host before tool dispatch; static inspection cannot prove that
    live fact. An attempt to provide operator-supplied support facts must fail
    at argument parsing. Preserve the explicit opt-in, target, and
    authorization-reference gates and assert the redacted receipt never
    contains a state-root path, target value, credentials, mailbox content, or
    raw model/tool data.
  - Validation: `poetry run pytest tests/test_fastmail_support_probe_script.py
    tests/test_fastmail_live_probe.py -q` initially fails for the distinct
    identity fixture.
  - Evidence (2026-09-13): the new distinct-ID inspection tests failed first
    because the command exposed no `inspect_saved_workflow` seam and still
    required `--support-facts`. After WMS5.2, the focused command, live-probe,
    and matrix suites passed with 24 tests.

- [x] WMS5.2 [implementation, GREEN] Replace the Fastmail probe's ambiguous
      `--package-name` interface with `--workflow-id` and derive all support
      identity from `inspect_saved_workflow` before host composition.
  - Spec: FR-004, FR-005, FR-011, AC-010.
  - Files/components: `scripts/run_fastmail_support_probe.py`, its focused
    tests, and only existing host inspection/invocation/receipt boundaries.
  - Depends on: WMS5.1.
  - GREEN: remove the `--support-facts` argument and its parser. Resolve the
    explicit workflow ID once through the registered immutable state, then
    derive and verify the exact material/package, policy, and profile used for
    classification. Let the configured host revalidate its existing reviewed
    read-only surface at invocation; do not duplicate or bypass that dynamic
    check. Invalid inspection or derived static facts must fail closed with zero
    host opens; stale dynamic surface facts must fail with zero tool dispatches.
  - Boundary: retain one narrow operator command; do not add a probe registry,
    a new host configuration path, live Fastmail/OAuth/MCP calls in pytest, or
    a second model/package fixture.
  - Validation: `poetry run pytest tests/test_fastmail_support_probe_script.py
    tests/test_fastmail_live_probe.py tests/test_workflow_model_support_matrix.py
    -q` and `poetry run ruff check scripts tests`.
  - Evidence (2026-09-13): the command now accepts `--workflow-id`, removes
    `--support-facts`, resolves registered identity before `LocalWorkflowHost.open`,
    and derives its material identity from the sealed model lock. The focused
    24-test suite and Ruff passed. A read-only inspection of the owner-local
    registration correctly refused with `saved package policy does not match`,
    before host opening, model loading, MCP access, or mailbox dispatch.

- [x] WMS5.4 [manual gate] Reconcile the owner-local Fastmail registration with
      its currently compiled immutable policy before allowing a live probe.
  - Spec: FR-004, FR-006, FR-011, AC-010.
  - Depends on: WMS5.2, WMS5.5, WMS5.6, WMS5.8, WMS5.9.
  - Evidence: read-only WMS5.2 inspection observed that registration
    `fastmail-inbox-triage-qwen-v4` maps to the intended sealed package ID but
    fails `saved package policy does not match`. This is a fail-closed static
    admission result, not a lost configuration or authorization to substitute
    a package. A direct read-only comparison confirmed the package and revision
    still match and an MCP binding remains present; only registered policy digest
    `d41486397f87362619da2441028081fc7231ddab6c167031d786903aafe56238`
    differs from currently compiled policy digest
    `2d0c80097f91a3d3a43aa75e6b3d327802daeed4ecbd0399ea8bf65546196ca4`.
  - Manual gate: inspect the exact cataloged revision and owner-approved
    registration/review procedure to identify the digest drift; then re-register
    only that same sealed package/revision against its current compiled policy
    and current reviewed binding. Re-inspect successfully before any live run.
    Do not reselect a different model/package, write credentials, or dispatch
    Fastmail as part of this task.
  - Validation: record only redacted registration, package, revision, policy,
    profile, and binding identities plus a successful post-reconciliation
    inspection. A failed reconciliation remains zero host-open/dispatch evidence.
  - Evidence (2026-09-13): the approved repair recreated the profile-bound OAuth
    connection, attached only its authenticated observed peer identity, and
    reviewed the existing read-only tool selection on that new pinned connection.
    The same cataloged package and revision then refreshed under the current
    compiled policy and current local principal. Post-reconciliation inspection
    confirmed compiled-policy identity, MCP binding, and owner presence without
    host opening, model loading, or Fastmail dispatch. Repository evidence
    intentionally omits owner-local paths, opaque identifiers, endpoint, scope,
    certificate, credentials, schemas, and mailbox data.

- [x] WMS5.5 [tests, implementation] Add an explicit owner-only refresh for a
      stale registration that preserves workflow, package, and revision identity.
  - Spec: FR-012, AC-011.
  - Files/components: `src/dynamic_agent_runner/workflow_host/registration.py`,
    `src/dynamic_agent_runner/workflow_host/host.py`, existing host CLI surface,
    and focused registration/host/CLI tests.
  - Depends on: WMS5.2.
  - RED: prove that the normal registration collision remains unchanged; an
    explicit refresh succeeds only for the existing workflow ID with the same
    package ID and revision digest after current profile/MCP binding validation.
    A changed package ID, revision digest, unavailable binding, or stale profile
    must leave the existing alias unmodified.
  - GREEN: add only one explicit refresh operation and operator command. Reuse
    the existing registration policy/profile/binding validation and private
    record store. Do not accept package paths, source handles, a replacement
    workflow ID, or a force flag.
  - Boundary: no Fastmail dispatch, model loading, package reselection, or
    arbitrary registration overwrite; MCP revalidation is the existing
    configured-client check.
  - Validation: focused registration, host, and CLI tests plus Ruff; then
    WMS5.4 must perform the owner-approved live-state reconciliation separately.
  - Evidence (2026-09-13): `refresh-registration --workflow-id` resolves only
    the existing cataloged package/revision and rejects a different local
    principal, package, revision, unavailable capability, mismatched profile,
    or unavailable MCP binding without changing the saved alias. For a changed
    MCP policy digest it verifies the existing reviewed snapshot against the
    current configured client, creates a new immutable binding for that same
    snapshot and policy, and validates it through the existing registration
    service. RED exposed the missing service, host, CLI, and policy-rebinding
    paths; GREEN ran `poetry run pytest tests/test_dar_authoring_registration.py
    tests/test_dar_authoring_host.py tests/test_dar_authoring_cli.py -q`
    (66 passed), focused Ruff, and `git diff --check`.

- [x] WMS5.6 [manual gate] Reconcile a detected configured MCP peer-certificate
  pin drift before WMS5.4 revalidates the reviewed surface.
  - Spec: FR-006, FR-012, AC-010, AC-011.
  - Depends on: WMS5.5, WMS5.7, and explicit owner authorization for the local
    connection update.
  - Evidence: the authorized WMS5.4 attempt reached the configured HTTPS MCP
    initialization boundary with its connection and credential records intact,
    then refused `HTTPS MCP peer identity does not match`; no registration,
    model, or Fastmail tool state changed.
  - Manual gate: establish one authenticated HTTPS initialization using the
    existing configured connection, retain the peer fingerprint only in local
    command state, and update the existing local attachment to that observed
    identity. Re-run the configured initialization successfully before WMS5.4.
    Do not change endpoint, scopes, connection, authentication, reviewed tool
    surface, package, or model; do not print or commit the fingerprint,
    credentials, or endpoint.
  - Validation: record only redacted success/failure and the absence of model
    loading, registration refresh, and Fastmail tool dispatch. A changed peer
    identity is not silently ignored or accepted by the transport.
  - Evidence (2026-09-13): after WMS5.7 supplied a profile-bound authenticated
    connection, an authenticated initialization observed a current peer identity
    and attached it only to owner-local host configuration. The subsequent normal
    `refresh-registration` initialized the pinned client successfully, made no
    model or Fastmail tool call, then failed closed because the prior reviewed
    surface snapshot belongs to the retired connection.

- [x] WMS5.7 [manual gate] Recreate the Fastmail MCP connection and OAuth
  authentication for the active configured host profile before completing WMS5.6.
  - Spec: FR-006, FR-012, AC-010, AC-011.
  - Depends on: explicit owner authorization for a browser-based OAuth
    authorization, and WMS5.5.
  - Evidence: the authorized WMS5.6 attempt successfully obtained the current
    authenticated peer identity but `attach_mcp_client` rejected it before any
    write because the saved MCP connection does not match the active
    `llama-cpp-v1` local-general-model profile. Existing connection and
    credential records remain intact; neither pin nor registration changed.
  - Manual gate: create one same-endpoint/same-scope connection under the
    active profile, complete the existing discovered OAuth authorization for
    that connection, and attach only the observed peer fingerprint. Retain no
    endpoint, scope, identifier, fingerprint, credential, browser URL, or
    mailbox content in repository evidence. Do not repurpose the old
    connection/authentication records across profiles.
  - Validation: establish current connection/profile equality and a successful
    pinned initialization before WMS5.6; make zero model or Fastmail tool calls.
  - Evidence (2026-09-13): one active OAuth connection and authentication now
    match the active configured profile. The local attachment was replaced only
    after authenticated peer observation. No endpoint, scope, identifier,
    fingerprint, credential, browser URL, mailbox content, model, or Fastmail
    tool data was retained in repository evidence.

- [x] WMS5.8 [tests, implementation] Permit an explicit fresh reviewed MCP
      surface snapshot when refreshing a saved registration after connection
      replacement.
  - Spec: FR-006, FR-012, AC-010, AC-011.
  - Depends on: WMS5.5, WMS5.6, WMS5.7.
  - RED: prove that an old snapshot tied to a replaced connection cannot be
    reused, while a caller-supplied current snapshot with the same declared
    tool/effect approvals can refresh the same workflow/package/revision.
    An absent, stale, mismatched, or unapproved snapshot must leave the alias
    unchanged.
  - GREEN: extend only `refresh-registration` with an optional explicit
    `--mcp-snapshot-id`. For MCP policies, use that supplied snapshot exactly
    when present; otherwise retain current behavior of revalidating the saved
    binding snapshot. Do not infer or copy approval from the prior connection,
    accept package paths or source handles, or add a force option.
  - Boundary: the operator must run the existing `review-mcp-surface` command
    and explicitly select tool approvals before supplying its opaque snapshot
    ID. No model loading or Fastmail tool dispatch occurs in either operation.
  - Validation: focused host and CLI tests, Ruff, and a redacted owner-local
    review followed by WMS5.4 refresh. Do not retain identifiers, schemas,
    endpoint, credentials, fingerprint, or mailbox data.
  - Evidence (2026-09-13): `refresh-registration` now accepts only the optional
    opaque `--mcp-snapshot-id`; an explicit snapshot is rebound to the current
    compiled policy and validated before replacing the existing alias. Without
    it, stale saved-binding behavior remains fail-closed. RED produced the
    missing host parameter and CLI argument failures. GREEN ran `poetry run
    pytest tests/test_dar_authoring_registration.py tests/test_dar_authoring_host.py
    tests/test_dar_authoring_cli.py -q` (66 passed), focused Ruff, and
    `git diff --check`.

- [x] WMS5.9 [tests, implementation] Allow an explicit refresh to claim only a
      legacy ownerless registration after all normal refresh validation passes.
  - Spec: FR-006, FR-012, AC-010, AC-011.
  - Depends on: WMS5.5, WMS5.8.
  - RED: prove that an ownerless registration refreshes the same workflow,
    package, revision, profile, and current reviewed MCP binding and writes the
    current local principal; a registration owned by any other explicit
    principal remains rejected and unmodified.
  - GREEN: treat `owner is None` as the sole legacy migration case inside the
    existing explicit refresh operation. Do not add an ownership override,
    migration command, alias replacement, path/source input, or force flag.
  - Boundary: ownership is claimed only after immutable identity, eligible
    capabilities, current profile, and current MCP binding validation succeed.
    No model loading or Fastmail tool dispatch occurs.
  - Validation: focused registration, host, and CLI tests plus Ruff; then rerun
    WMS5.4 with the explicit fresh surface snapshot. Repository evidence must
    remain redacted.
  - Evidence (2026-09-13): only a missing legacy `owner` is eligible for the
    existing refresh flow; its current principal is persisted only with the
    already validated refreshed registration. Any nonempty different owner still
    fails before an alias write. RED reproduced rejection of an ownerless
    record. GREEN ran `poetry run pytest tests/test_dar_authoring_registration.py
    tests/test_dar_authoring_host.py tests/test_dar_authoring_cli.py -q` (67
    passed), focused Ruff, and `git diff --check`.

- [x] WMS5.3 [manual gate] Record one Fastmail live receipt only after WMS5.2
      is green, the registered identity and reviewed read-only surface are
      re-inspected, and a fresh explicit operator authorization is supplied.
  - Spec: FR-004, FR-005, FR-011, AC-004, AC-010.
  - Depends on: WMS5.2, WMS5.4.
  - Manual gate: run exactly one bounded read-only candidate with the registered
    workflow ID, explicit opt-in, target, and authorization reference. Preserve
    only the fixed redacted receipt; do not commit a state-root path, target,
    authorization value, credentials, mailbox content, raw model/tool data, or
    session transcript.
  - Evidence: classify Fastmail as live-supported only if the fresh receipt
    binds the registered workflow, derived sealed package/material identity,
    profile, and host-revalidated reviewed surface. Otherwise retain the current
    absence of live evidence.
  - Evidence (2026-09-13): one explicit authorized read-only probe completed
    against the repaired registered workflow. Its fixed redacted receipt reported
    `supported`, one dispatch, and no prohibited target, authorization,
    credential, endpoint, path, prompt, mailbox, or raw model/tool fields. The
    temporary receipt was verified and discarded after this durable redacted
    record; no second dispatch was performed.

  - Review disposition (2026-09-13): a reduced-independence sequential Council
    architecture triad required the static registered-identity and dynamic MCP
    surface checks to remain distinct. Ponytail retained the existing
    inspection and host-invocation boundaries, rejecting a probe registry,
    second surface validator, or a new test module. WMS5 is implementation-ready
    with the corrected focused test targets and dispatch boundary.

## Checkpoints

- WMS1: pure, side-effect-free classification and non-transferable evidence.
- WMS2: fully offline Fastmail, embedding, floorplan, structured-output,
  stateful-context, and tool-pack workflow coverage.
- WMS3: human-gated Fastmail and floorplan receipt paths with fake authorization
  coverage.
- WMS4: documented coverage and validation record.
- WMS5: Fastmail probe derives registered workflow/package identity before a
  newly authorized live receipt can be recorded.

## Validation

- `poetry run pytest tests/test_workflow_model_support_matrix.py -q`
- `poetry run pytest -q`
- `poetry run ruff check src tests`

## Boundary Notes

- Live Fastmail and floorplan work remain per-run human authorization boundaries.
- Package/material locks are authoritative; adapters do not silently substitute
  files or providers.
- Three exact MLX package rows are recorded by MLE6, MLE7, and MLE8 evidence;
  each is non-transferable despite their shared embedding workflow profile.
  Sandboxed write/shell and runner-owned RAG remain excluded until
  their owning feature contracts are implemented.
