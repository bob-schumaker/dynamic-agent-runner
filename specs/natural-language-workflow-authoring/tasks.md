# Natural-Language Workflow Authoring Tasks

## Status

NLA-1 and NLA-2 are complete; NLA-3 is in progress and later slices remain
implementation candidates.
Complete tasks in dependency order and record RED and GREEN evidence in this
file. The
authoritative requirements are
[`spec.md`](spec.md); the slice design is [`plan.md`](plan.md).

## Scope Rules

- Agent Engineering asks only irreducible workflow-contract questions. When a
  required capability or workflow-local tool is absent, it creates repository
  implementation guidance; it does not write executable code or tool assets.
- DAR owns sealed artifacts, capability binding, approved sandbox dispatch,
  execution limits, tracing, redacted registration, and saved-workflow
  invocation. It does not own SVG, floorplan, PCAP, protobuf, or other domain
  semantics.
- Do not add an authoring model, authoring-model configuration, model/server
  lifecycle, format catalog, tool-package discovery, or new binary ingress.
- All automated tests use fakes for model, network, GUI, MCP, and tool-package
  collaborators. Controlled temporary filesystem fixtures are allowed only to
  test sealed ingress and sandbox containment; do not access a caller's live
  workspace or a real external tool.

## NLA-1 — Closed Registration Contract

- [x] NLA-1.1 [RED] Add `tests/test_natural_language_workflow_authoring.py`
      for the canonical workflow contract, declarative workflow definition, and
      `ready` / `unavailable` DAR result models.
  - Spec: FR-2, FR-5, FR-6
  - Components: `workflow_host/host.py`, existing authoring-material/output and
    registration boundaries
  - Cases: definition-to-contract mismatch; invalid definitions; prohibited
    paths, handles, credentials, and executable tool code; known result status;
    no material-set ID, path, profile ID, receipt, or source content in returned
    failures.
  - Validation:
    `poetry run pytest tests/test_natural_language_workflow_authoring.py -q`
  - Expected RED: no closed registration transaction or result contract exists.
  - RED: `poetry run pytest tests/test_natural_language_workflow_authoring.py -q`
    failed during collection with `ModuleNotFoundError` for
    `workflow_authoring_registration`.

- [x] NLA-1.2 [GREEN] Implement the closed canonical contract, declarative
      definition validation, and immutable DAR result values.
  - Spec: FR-5, FR-6
  - Components: `workflow_host/workflow_authoring_registration.py`
  - Depends on: NLA-1.1
  - Requirements: accept only a completed canonical contract and declarative
    definition; reject paths, handles, credentials, executable tool code, and
    control-plane values; accept only the existing declarative workflow artifact
    paths; return only `ready` or `unavailable`. Do not persist, stage,
    register, or add a CLI command in this slice.
  - Validation:
    `poetry run pytest tests/test_natural_language_workflow_authoring.py -q`
  - GREEN: targeted contract tests passed with 10 tests; Ruff passed for the new
    module and test.

## NLA-2 — Multimodal Profile Capability and Sealed Image Delivery

- [x] NLA-2.1 [RED] Add profile, ingress, adapter, registration, and runner
      tests for one image-capable llama.cpp profile.
  - Spec: FR-3; Multimodal Local-Profile Execution
  - Components: `tests/test_dar_authoring_profiles.py`,
    `tests/test_dar_authoring_workspace_ingress.py`,
    `tests/test_dar_authoring_runner.py`
  - Cases: exact model/adapter match; text-only and missing profile rejection;
    altered hash or media-type rejection; image bytes reach only the selected
    adapter; no original workspace path reaches the model; text workflows stay
    unchanged.
  - Validation:
    `poetry run pytest tests/test_dar_authoring_profiles.py`
    `poetry run pytest tests/test_dar_authoring_workspace_ingress.py`
    `poetry run pytest tests/test_dar_authoring_runner.py -q`
  - Expected RED: current profile capability and adapter path are text-only.
  - RED: the focused command ran 57 tests: 54 passed and 3 failed because the
    vision-profile factory, sealed-image consumer, and runner multimodal gate
    do not exist.

- [x] NLA-2.2 [GREEN] Implement profile-derived `multimodal_input` capability,
      sealed-image consumption, and configured llama.cpp vision adapter wiring.
  - Spec: FR-3; Multimodal Local-Profile Execution
  - Components: `workflow_host/profiles.py`, `workflow_host/host.py`,
    `workflow_host/workspace_ingress.py`, `local_models.py`
  - Depends on: NLA-2.1
  - Requirements: derive registration eligibility from the selected profile;
    reject a missing vision backend/projector/configuration before a model call;
    do not alter text `materialize()` semantics or create image-specific caller
    paths.
  - Validation: run the NLA-2.1 command plus the affected existing profile,
    ingress, and local-model suites.
  - GREEN: profile-derived multimodal admission, sealed-image materialization,
    text-profile rejection, dedicated llama.cpp sealed-image request shaping,
    profile-derived registration eligibility, and runner delivery through a
    declared image input are implemented and covered. The focused and affected
    profile, ingress, runner, vision-adapter, and local-model tests passed with
    214 tests.

## NLA-3 — Generic Workflow-Local Tool Runtime

- [x] NLA-3.1 [RED] Add descriptor, runner, and sandbox tests for a declared
      deterministic local tool.
  - Spec: FR-6; Workflow-Local Deterministic Tooling
  - Components: workflow descriptor/policy, runner, sandbox, and their tests
  - Cases: fixed identity; sealed input/output; finite limits; bounded result;
    declared failure result; rejection of undeclared filesystem, network,
    process, or tool access.
  - Validation: run the focused descriptor, policy, runner, and sandbox tests.
  - Expected RED: no generic local-tool contract or approved dispatch path
    exists.
  - RED: `poetry run pytest tests/test_dar_authoring_local_tools.py -q` failed
    during collection with `ModuleNotFoundError` for `workflow_host.local_tools`.

- [ ] NLA-3.2 [GREEN] Implement generic approved sandbox dispatch for an
      already implemented workflow-local tool.
  - Spec: FR-4, FR-6; Workflow-Local Deterministic Tooling
  - Depends on: NLA-3.1
  - Requirements: validate an implementation-owned asset at package validation;
    dispatch it with sealed artifacts, limits, tracing, and failure containment;
    define and test the deterministic executable I/O and result envelope before
    dispatch; add no SVG or other domain parser to DAR.
  - Validation: run the NLA-3.1 command and existing no-tool and reviewed-tool
    regression suites.
  - Progress: the package-contained asset, sealed role, finite input/output,
    timeout, failure boundary, and descriptor admission are implemented with an
    injected executor. The deterministic ABI is sealed raw artifact bytes on
    stdin and one bounded UTF-8 JSON evidence object on stdout; malformed
    output is a redacted failure. Registration-bound binary artifacts now
    materialize only through the host preparation boundary for those bindings.
    The runner now creates host-registry bindings from cataloged assets and
    role-matched sealed binary artifacts. Staging grants execute permission
    only to descriptor-declared regular local-tool assets, which policy then
    revalidates. A trusted deterministic fixture now exercises the sealed ABI
    through permissive macOS `sandbox-exec`; this proves the execution handoff,
    not untrusted-tool isolation, which is deferred to
    `local-tool-sandbox-hardening`. `LocalWorkflowHost.open()` now supplies
    that executor and admits `local_tool_sandbox` only while its runner exposes
    it. Traces and a workflow-owned implementation asset remain required before
    this task is complete.

- [ ] NLA-3.3 [GREEN] Add an implementation-owned floorplan fixture with a
      workflow-local SVG validator and invocation coverage.
  - Spec: FR-3, FR-4; Workflow-Local Deterministic Tooling
  - Depends on: NLA-2.2, NLA-3.2, NLA-4.2
  - Cases: valid SVG succeeds; invalid SVG produces the workflow-declared
    failure without sandbox details; trusted image ingress works through the
    saved workflow name; dry run avoids ingress, local-tool, and model execution.
  - Validation: focused floorplan fixture and `dar-package invoke` tests.
  - Decision: validate the shaped terminal output through a declared host
    post-processing validator; do not expose generated SVG as a model tool
    argument.

## NLA-4 — Internal Composition and Opaque-Binary Tools

- [x] NLA-4.1 [RED] Add façade integration tests for authoring-material
      issuance, output creation/finalization, staging, registration, and
      rollback on failed registration.
  - Spec: FR-2, FR-5
  - Depends on: NLA-1.2, NLA-2.2
  - Cases: unavailable profile capability, profile mismatch, invalid definition,
    registration failure, and name collision leave no partial saved registration
    and expose no internal detail.
  - Validation:
    `poetry run pytest tests/test_natural_language_workflow_authoring.py -q`
  - Progress: mismatched definitions now fail before persistence; valid
    definitions exercise internal material/output/finalization/registration
    composition through fakes; finalization failure is redacted and does not
    reach registration; package-name collision and registration/profile failure
    are redacted. The focused suite passed with 15 tests.

- [x] NLA-4.2 [GREEN] Complete transactional registration composition and
      executable handoff.
  - Spec: FR-2, FR-4, FR-5
  - Depends on: NLA-4.1
  - Requirements: use the existing host collaborators rather than duplicate
    their persistence or registration logic; return only workflow name, input
    contract, output contract, and invocation action. Add the skill-facing
    `LocalWorkflowHost.register_authored_workflow()` method and
    `dar-package register-authored-workflow` command only here.
  - Validation: run the NLA-4.1 command plus existing authoring-output,
    registration, preparation, and CLI tests.
  - GREEN: the host composes existing authoring-material, output,
    finalization, selection, and registration collaborators behind the closed
    `register_authored_workflow()` result. The stdin-only versioned
    `dar-package register-authored-workflow --definition-stdin` command parses
    only a complete canonical contract and declarative definition, returns the
    redacted façade result, and was verified both with a fake host and a real
    temporary host followed by saved-workflow dry run. Focused authoring and
    CLI tests passed with 57 tests.

- [x] NLA-4.3 [RED] Add reviewed tool-package and opaque-artifact tests.
  - Spec: FR-7; Opaque-Binary Artifact Tool Analysis
  - Components: descriptor/policy, reviewed binding control plane, tool binding,
    workspace ingress, and runner tests
  - Cases: exact name and allowlist capture; unknown/stale package rejection;
    non-artifact-aware tool rejection; changed sealed artifact rejection;
    bounded evidence; no caller path or raw bytes in a model prompt.
  - Validation: run the focused reviewed-binding, descriptor, ingress, and
    runner tests.
  - Expected RED: no named reviewed package or opaque-artifact tool contract
    exists.
  - RED progress: the focused reviewed-package control-plane tests fail during
    collection with `ModuleNotFoundError` for `reviewed_tool_packages`.
  - Progress: the named reviewed-package control plane now persists an exact
    binding and tool allowlists, rejects unknown or changed bindings, and
    rejects non-artifact-aware tool selection. The runner now constructs a
    normal host-registry binding for a declared artifact tool before its
    no-MCP branch. It keeps verified binary bytes behind a private reader and
    exposes no model-selectable artifact ID, path, or bytes; the model sees
    only bounded evidence. `LocalWorkflowHost` now owns the named reviewed
    package control plane and accepts only host-configured executor bindings.
    The opaque-reference ingress path now also rejects changed sealed content
    before it can reach the reviewed binding. Focused reviewed-package,
    descriptor, ingress, preparation, and runner suites pass.

- [ ] NLA-4.4 [GREEN] Implement named reviewed tool-package resolution and
      opaque-binary artifact binding.
  - Spec: FR-7; Opaque-Binary Artifact Tool Analysis
  - Depends on: NLA-4.3
  - Requirements: model only bounded evidence; use one format-agnostic opaque
    artifact contract for fake network and protobuf packages; no fallback,
    discovery, installation, or DAR format registry.
  - Validation: run the NLA-4.3 command plus existing MCP approval/budget and
    non-artifact tool regressions.

## NLA-5 — Agent Engineering Integration and Release

- [ ] NLA-5.1 [RED] Add fresh-session Agent Engineering regressions for the
      floorplan and named tool-package requests.
  - Spec: FR-1, FR-5, FR-7
  - Components: `tests/test_agent_engineering_plugin.py`, source Agent
    Engineering payload
  - Cases: the floorplan request asks only for output format; explicit `return
    SVG` asks nothing; each omitted required model, input, or output asks only
    its smallest question; examine/analyze defaults to text; named opaque-binary
    tools do not trigger a binary-format question; unknown, stale, and
    non-artifact-aware named packages are unavailable without guidance or
    registration.
  - Validation: `poetry run pytest tests/test_agent_engineering_plugin.py -q`
  - Expected RED: the payload still exposes the material-set control plane.

- [ ] NLA-5.2 [GREEN] Migrate `agent-development` to design-first authoring.
  - Spec: FR-1, FR-5, FR-6
  - Depends on: NLA-1.2, NLA-2.2, NLA-3.2, NLA-3.3, NLA-4.2, NLA-4.4, NLA-5.1
  - Requirements: create repository guidance when an image runtime or local
    tool is missing. Guidance must state the workflow contract, missing
    boundary, sealed I/O, execution limits, failure result, and acceptance
    tests. It must contain no executable asset/source, host detail,
    control-plane value, or extra question. An unknown, stale, or
    non-artifact-aware reviewed package returns `unavailable` without guidance
    or registration. Submit only requirements-satisfied declarative definitions
    to `register_authored_workflow`.
  - Validation: `poetry run pytest tests/test_agent_engineering_plugin.py -q`

- [ ] NLA-5.3 [GREEN] Repackage and validate the Agent Engineering plugin.
  - Spec: Release and Compatibility Notes
  - Depends on: NLA-5.2
  - Requirements: regenerate plugin payload and direct-plugin baseline only via
    the established packager; do not hand-edit generated trees, baseline
    digests, lock files, or receipts.
  - Validation: established plugin packager, direct-plugin baseline test, and
    installed-payload search proving no user-facing `material_set_id` remains.

- [ ] NLA-5.4 [validation] Run release validation in order.
  - Spec: Validation; Release and Compatibility Notes
  - Depends on: NLA-2.2, NLA-3.3, NLA-4.2, NLA-4.4, NLA-5.3
  - Validation:
    1. affected host, model, ingress, sandbox, tool, CLI, and plugin suites;
    2. `poetry check` and `poetry build` after assigning the DAR runtime release
       version;
    3. DAR wheel/package smoke check before updating the Agent Engineering DAR
       pin;
    4. plugin package, publish, install, and installed-payload verification.
  - Release order: DAR runtime first, then Agent Engineering pin, package,
    publish, install, and verification.

## Stop Conditions

- Stop and rescope if the generic local-tool sandbox cannot enforce sealed I/O,
  finite limits, and no ambient filesystem/network/process/tool access.
- Stop and rescope if image transport requires caller filesystem paths or a
  text-only profile would be registered for image input.
- Stop and rescope if opaque-binary analysis requires DAR to recognize a format
  or grants raw bytes/path access to a model.
- Stop and rescope if implementation guidance requires Agent Engineering to
  generate executable code, create a host-wide tool, or expose a control-plane
  identifier.
