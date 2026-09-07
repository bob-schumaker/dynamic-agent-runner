# Natural-Language Workflow Authoring Implementation Plan

## Status

Ready for implementation. This plan implements
[`spec.md`](spec.md) in test-first, independently shippable slices. It does not
authorize a model download, llama.cpp lifecycle management, an unreviewed tool
installation, or live external calls in automated tests. The executable
checklist is [`tasks.md`](tasks.md).

## Goal

Replace the current Agent Engineering authoring ceremony—human-issued material
manifests, opaque handles, and a separate select/register handoff—with a
minimal-question workflow-design process and one host-owned
`register_authored_workflow`
registration operation. It returns a saved executable workflow when all
requirements exist; otherwise it returns repository-appropriate implementation
guidance, never model-authored code.

The first delivered workflow is image-to-SVG through an already configured,
image-capable llama.cpp profile. A later additive slice authors tool-backed
opaque-binary workflows, such as packet-capture analysis, without teaching the
skill individual binary formats.

## Separation of Responsibilities

### DAR platform requirements

These are runtime capabilities DAR must implement, test, version, and release.
They are not steps a user takes to create a workflow.

| DAR capability | DAR-owned responsibility |
| --- | --- |
| Authoring transaction | Accept the skill's canonical contract and declarative workflow definition, issue internal material, validate, stage, bind, register, and redact failure details. |
| Image execution | Bind only an image-capable local profile and deliver a sealed image to its llama.cpp adapter. |
| Local-tool runtime | Run a workflow-declared deterministic tool in the approved sandbox with sealed inputs, budgets, bounded results, and no ambient host access. |
| Opaque-binary tools | Resolve a reviewed named tool package, bind an artifact-aware tool, and enforce artifact, tool, result, and budget limits. |
| Compatibility | Preserve existing saved-workflow invocation, text artifacts, direct human control-plane commands, and non-artifact MCP tools. |

DAR does not provide an authoring model, an authoring-model configuration, SVG
or other domain semantics, a format registry, model/server lifecycle,
tool-package discovery, or a user control-plane workflow.

### Automatic workflow-building process

This is the complete user-visible process after DAR ships the platform
requirements:

1. The user describes the desired workflow in natural language.
2. Agent Engineering derives a contract and identifies required runtime and
   workflow-local tool capabilities. It asks one direct question only when a
   material contract choice remains unknown; for example, the floorplan request
   asks for output format.
3. The user answers, if needed. For examine/analyze requests with no output
   artifact or destination, Agent Engineering uses the deterministic plain-text
   default.
4. If an implementation requirement is unmet, Agent Engineering creates a
   repository work-item specification that says what must be implemented for
   the workflow to be complete. It does not write executable code.
5. Otherwise Agent Engineering creates the completed canonical contract and
   declarative workflow definition, then submits both to DAR internally.
6. DAR performs the registration transaction and returns `ready` or
   `unavailable`.
7. Agent Engineering shows either the implementation guidance or the saved
   workflow name, its input/output contract, and its invocation action.

The user never creates a manifest, material set, workflow-definition file,
package path, authoring profile, tool binding, or registration. Missing generic
runtime capability or workflow-local tooling produces implementation guidance;
an absent configured profile or reviewed named tool package is an `unavailable`
result, not a configuration question disguised as authoring.

## Current-State Anchors

| Concern | Current owner | Required change |
| --- | --- | --- |
| Private materials and generated package files | `workflow_host/authoring_materials.py`, `authoring_outputs.py`, and `host.py` | Reuse inside the façade; do not expose their IDs to the skill or user. |
| Saved-package composition | `LocalWorkflowHost.finalize_and_select_authored_output`, `register`, and `invoke_saved` in `workflow_host/host.py` | Compose internally after successful authoring. |
| Skill-facing registration CLI | `dar_package_cli.py` | Add one closed registration command that accepts only a completed contract and declarative definition, then returns the registration protocol. Retain the existing low-level commands for explicit control-plane users. |
| Profile capability contract | `workflow_host/profiles.py` | Add an image-capable local profile requirement and derive registration capabilities from the selected profile. |
| Host adapter factory | `_create_model_adapter` in `workflow_host/host.py`; `local_models.py` | Add a dedicated, configured llama.cpp vision adapter; do not reinterpret the existing text-only adapter. |
| Trusted artifacts | `workflow_host/workspace_ingress.py` and `preparation.py` | Reuse the no-follow, hash-bound private copy. Keep `materialize()` text-only; add dedicated sealed-image and opaque-binary consumers. |
| Workflow policy and tools | `workflow_host/descriptor.py`, `policy.py`, `mcp_binding.py`, `mcp_tools.py`, and `authorized_tools.py` | Add explicit artifact-aware tool binding and a named reviewed tool-package resolver. Current reviewed MCP bindings have no package-name abstraction. |
| Current skill behavior | `plugins/agent-engineering/payload/dar-workflow-authoring/references/dar-runtime-profile/agent-development.md` | Replace the material-set/create/write/finalize transcript with the design-first guidance and registration protocol, then regenerate the plugin payload. |

## Boundary Design

### Selected design: a deep host façade

`WorkflowAuthoringRegistrar` is a host-owned service under `workflow_host/`.
Its single public operation accepts the skill's completed
canonical contract and declarative workflow definition, then returns exactly
one versioned result:

- `ready(workflow_name, input_contract, output_contract, invocation)`; or
- `unavailable(capability, requirement)`.

It owns internal material issuance, package output creation, validation,
staging, registration, collision-safe naming, and redaction. The active Agent
Engineering model supplies one internal fixed canonical contract and
declarative workflow definition after clarification and requirement checking.
The definition contains no executable local-tool code, path, host
configuration, profile ID, manifest, receipt, or opaque handle. Tests supply
the same values as fixtures. The host rejects a definition that does not match
its supplied canonical contract.

This is preferable to extending the Agent Engineering skill with another
sequence of low-level `dar-package` commands. That alternative repeats
control-plane knowledge in a user-facing agent and recreates the
`material_set_id` failure mode. The declarative workflow definition is not a
package path, executable implementation, or authoring-output handle; it is a
bounded skill-to-host value that DAR owns once it validates and persists it.

### Artifact and tool-package rules

The common deterministic tool ABI is sealed raw artifact bytes on standard
input and one bounded UTF-8 JSON evidence object on standard output. DAR never
places a caller path or raw bytes in a model prompt. The JSON object is the
tool's declared evidence result; malformed, oversized, or failed execution is
a bounded declared failure rather than a host detail.

For terminal-output validation, use the same bounded JSON-evidence shape as a
separate host post-processing ABI: the declared validator receives the shaped
terminal message on standard input after model execution. It is not exposed to
the model and receives no workspace artifact. The first workflow-owned SVG
validator implements SVG semantics; DAR only dispatches and bounds it.

Do not create a binary-format registry. A workflow input is either a declared
image artifact or an `opaque_binary_artifact`; ingress keeps its existing
generic copy-and-hash boundary. A typed host-only consumer rechecks the
registration, media type, hash, and byte bound before either an image adapter
or an artifact-aware tool receives it.

Introduce a narrow `ReviewedToolPackage` record rather than a general package
manager. It maps one stable host-created name to an exact current reviewed
capability binding and allowlisted tool descriptors. A workflow stores that
identity at registration. Unknown, stale, and non-artifact-aware packages fail
closed; there is no discovery, installation, or fallback.

## DAR Platform Delivery Slices

Every slice starts with focused RED tests, records the expected failure, then
implements only enough code to turn that slice GREEN. All unit and integration
tests use fixed declarative-definition fixtures, fake model adapters, artifact
readers, and tools.

### S1 — Authoring transaction contract

1. Add `tests/test_natural_language_workflow_authoring.py` for the closed
   canonical contract, declarative workflow definition, and result models. Test
   accepted and rejected contracts, definition-to-contract mismatch, and the
   two stable DAR result statuses.
2. Add rejected-input and redaction cases: invalid contract or definition,
   definition-to-contract capability mismatch, unknown result status, and no
   `material_set_id`, path, profile ID, receipt, or source content in a
   user-facing failure.
3. Implement `workflow_host/workflow_authoring_registration.py` with internal fixed
   contract/definition types and immutable public result values. Keep package
   persistence out of this slice. Keep implementation guidance outside
   DAR: it is an Agent Engineering repository-artifact outcome.

Exit: DAR has an executable registration contract, while Agent Engineering owns
natural-language interpretation, clarification, contract creation,
implementation guidance, and declarative-definition creation.

### S2 — Profile-derived multimodal capability and sealed image delivery

1. Add RED tests in `tests/test_dar_authoring_profiles.py`,
   `tests/test_dar_authoring_workspace_ingress.py`, and
   `tests/test_dar_authoring_runner.py` for an image-capable llama.cpp profile,
   a text-only rejection, exact model/adapter matching, changed hash or media
   type rejection, and unchanged text workflow behavior.
2. Extend `LocalModelProfileControlPlane` in `profiles.py` with one explicit
   local multimodal profile requirement whose capability set includes
   `text_generation` and `multimodal_input`. Keep its adapter allowlist
   separate from existing text-only profile entries.
3. Replace `LocalWorkflowHost.register()`'s fixed available-capability set with
   the configured profile's validated capabilities. Registration remains the
   authority: a text-only profile cannot register an image workflow.
4. Add a sealed-image materialization path beside, not inside,
   `WorkspaceIngressService.materialize()`. It may read the private verified
   bytes needed to construct the adapter request, but it must never pass the
   original workspace path to the adapter or model.
5. Add a dedicated llama.cpp vision adapter/configuration in `local_models.py`
   and host factory wiring in `host.py`. Its fake backend tests prove its image
   message shape and model identity check. The implementation must reject a
   missing vision backend/projector/configuration before any model call.

Exit: a registered workflow can deliver one sealed image only to the exact
configured image-capable adapter; text workflows behave as before.

### S3 — Internal authoring-to-saved-workflow composition

1. Add RED façade tests with fixed declarative workflow definitions. Assert the
   service internally issues canonical workflow intent as authoring material,
   creates/writes/finalizes output, stages it, registers a collision-safe saved
   name, and returns the executable handoff.
2. Add failure tests for a missing, mismatched, or invalid definition, profile
   mismatch, registration failure, and name collision. Each must produce the
   stable `unavailable` result without leaking a host detail; no partial saved
   registration may remain on failure.
3. Add `LocalWorkflowHost.register_authored_workflow()` without adding a host model,
   profile, configuration field, or lifecycle. The host, not the skill,
   derives package names, target-profile binding, material records, output
   handles, and registration aliases. The transaction composes the existing
   authoring-material, authoring-output, finalization, and
   `WorkflowRegistrationService` boundaries; it does not duplicate any of them.
4. Add the `dar-package register-authored-workflow` closed command in
   `dar_package_cli.py`. It accepts only a completed canonical contract and
   declarative definition on standard input. Its v1 input is one JSON object
   with exactly `format_version`, `contract`, and `definition`; each nested
   value admits only the fields of its closed DAR contract,
   returns one versioned façade result, and rejects executable tool code, paths,
   package IDs, profile IDs, endpoints, credentials, manifests, and authoring
   handles. Clarification and implementation guidance remain in Agent
   Engineering.

Exit: a requirements-satisfied floorplan design can produce a saved workflow
from definition to handoff without exposing the prior low-level authoring
sequence.

### S4 — Workflow-local deterministic tooling and executable handoff

1. Add RED descriptor, runner, and sandbox tests for a workflow-declared local
   deterministic tool: fixed identity, sealed input/output, finite limits,
   bounded result, and rejection of undeclared filesystem, network, process, or
   tool access.
2. Add the generic approved sandbox dispatch boundary. It validates and runs a
   local-tool asset but contains no SVG or other domain-specific parser.
3. Add an implementation-owned floorplan fixture with a workflow-local SVG
   validator. Its valid and invalid results prove the workflow, rather than DAR,
   owns SVG semantics; the Agent Engineering regression proves that the skill
   only wrote the validator's implementation specification, not the fixture or
   validator code.
4. Extend `dar-package invoke` tests to show the ready result's invocation
   action accepts a trusted workspace image through the saved name, and a dry
   run still avoids ingress, tool execution, and model execution.

Exit: the floorplan example has an executable image-to-SVG path whose validator
is workflow-local, while DAR remains a generic sandbox dispatcher.

### S5 — Reviewed tool packages and opaque-binary artifact analysis

1. Add RED tests for a host-owned `ReviewedToolPackage` control plane: exact
   name lookup, immutable reviewed binding/allowlist capture, stale binding
   rejection, unknown-name rejection, and no fallback to another package.
2. Extend the descriptor/policy contract with an explicit
   `opaque_binary_artifact` input and an artifact-aware tool declaration. The
   declaration must bind to one reviewed tool package and cannot be combined
   with arbitrary model-provided artifact IDs or tool names.
3. Add a host-only artifact-tool binding that revalidates the sealed artifact's
   registration, role, hash, size, and declared kind before invoking a tool.
   Give the tool a verified artifact reader/reference, never the caller path or
   raw content in the model prompt. Preserve existing MCP read-only and
   approval/budget behavior for non-artifact tools.
4. Add fake network and protobuf tool-package tests. Both use the same opaque
   artifact contract and return bounded evidence; neither adds a DAR format
   allowlist. Add negatives for a non-artifact-aware tool, altered artifact,
   excessive result, stale package, and declared-tool mismatch.
5. Have Agent Engineering include the named tool package in the canonical
   contract. DAR resolves only that package during validation. “Examine network
   dumps for packet contents using the network tools in
   `<tool-analysis-package>`” defaults to text analysis; unavailable
   package/capability results occur before package creation or registration.

Exit: binary format knowledge stays with reviewed tools, while DAR enforces the
artifact, binding, result, and budget boundaries.

## Agent Engineering Process Integration and Release

### S6 — Automatic process migration, regression, and release

1. Replace the material-set instructions and low-level command transcript in
   the source Agent Engineering payload with a design-first relay: ask only the
   minimum clarification, create a repository implementation specification for
   every unmet requirement, and submit only a requirements-satisfied canonical
   contract plus declarative workflow definition to
   `register_authored_workflow`. It must
   never generate executable code or a local-tool asset. Remove any instruction
   to ask for a manifest, material set, authoring-model setup, output handle, or
   manual select/register handoff for this path.
2. Add a fresh-session fixture/regression in
   `tests/test_agent_engineering_plugin.py` that reproduces the floorplan
   request and proves the only visible question is the output format, followed
   by repository guidance when its image runtime or validator is absent. Assert
   that the guidance states the workflow contract, missing boundary, sealed I/O,
   execution limits, failure result, and acceptance tests, and contains no
   executable asset, generated source, control-plane value, or extra question.
   Add cases proving that an explicit `return SVG` needs no clarification and
   that each omitted required model, input, or output value yields only its
   smallest required question.
   Add the network-tool-package fixture proving no binary-format question is
   asked and that an unknown, stale, or non-artifact-aware named package returns
   `unavailable` without registration or implementation guidance.
3. Regenerate `.codex-plugin/generated/agent-engineering` from the payload and
   update direct-plugin baseline fixtures only through the established
   packager. Do not hand-edit generated manifests or lock files.
4. Run focused suite groups first, then the affected host, model, CLI, and
   plugin suites. Run `poetry check`, `poetry build`, and package/installed-wheel
   smoke checks after the runtime release version is assigned.
5. Release the DAR wheel first because `register-authored-workflow`, multimodal
   execution, and artifact-aware tool binding are runtime behavior. Then update
   the Agent
   Engineering DAR pin, package the plugin, publish/install it, and verify the
   installed payload contains the façade instructions and no user-facing
   `material_set_id` requirement.

Exit: after the DAR runtime release is available, the installed skill performs
the seven-step automatic process above without exposing DAR platform work to
the user.

## Validation Matrix

| Requirement | Evidence |
| --- | --- |
| One visible clarification for the floorplan prompt | Deterministic request-analysis and fresh Agent Engineering fixture tests. |
| Missing implementation becomes guidance, not generated code | Agent Engineering fixture asserts a repository spec and no executable local-tool asset. |
| No exposed authoring internals | Façade JSON/result contract tests plus plugin-text regression search. |
| Exact image-capable llama.cpp model only | Profile, adapter, registration, and runner fake tests. |
| Image is sealed and path-free | Ingress/hash/media-type tests and fake adapter request assertions. |
| Saved executable SVG workflow | End-to-end fake host registration/invocation after the validator is implemented, plus workflow-local SVG valid/invalid tests; one separately authorized manual local run. |
| No binary format catalog | PCAP and protobuf fake tool packages using the identical opaque-artifact schema. |
| Reviewed package/tool enforcement | Resolver, descriptor, binding, stale/unknown, budget, and result-bound tests. |
| Existing behavior preserved | Existing authored-workflow, ingress, MCP, runner, CLI, and plugin suites. |

## Release and Compatibility Notes

- This is a DAR runtime release followed by an Agent Engineering plugin release;
  repackaging the plugin alone cannot supply the new host behavior.
- Agent Engineering is the authoring model. DAR validates and commits its
  requirements-satisfied declarative workflow definition; it does not add an
  authoring-model profile, configuration, selection flow, or lifecycle.
- Existing direct authoring commands remain available for explicit human
  control-plane callers. The new façade is additive and is the only path the
  migrated skill uses.
- Existing text artifact ingress, text-only profiles, no-tool workflows, and
  non-artifact MCP tools retain their current contracts and test coverage.
- Do not hand-edit `poetry.lock`, generated plugin trees, baseline digests, or
  release receipts.
