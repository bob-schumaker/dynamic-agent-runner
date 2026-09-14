# Workflow Model Support Matrix Specification

Status: Implemented through WMS5; one redacted Fastmail live receipt is recorded
Version: 0.1.0
Owner: Repository maintainers
Date: 2026-09-13

## Objective

Provide a single, capability-gated support matrix for DAR's implemented
workflow families. It must make evidence and eligibility auditable without
claiming that a workflow is portable to a model or provider that lacks its
required capabilities or locked materials.

## User Stories

- As a maintainer, I want deterministic support rows for every registered
  workflow profile and model adapter so that unsupported combinations are not
  mistaken for regressions.
- As an operator, I want a redacted eligibility receipt before a live Fastmail
  run so that live authorization remains separate from ordinary tests.
- As a package author, I want embedding support evaluated against the workflow's
  locked material closure and ABI, rather than against a named global model list.
- As a maintainer, I want multimodal conversion/generation, structured output,
  session/context, and tool-pack composition represented by explicit profiles
  so that generic tests do not conceal workflow-level gaps.

## Functional Requirements

- [MUST] FR-001: Define one machine-readable profile contract for each matrix
  row. A profile declares workflow family, required model capabilities, required
  sealed material roles, required ABI/provider capabilities, execution mode,
  and whether human authorization is required.
- [MUST] FR-002: Classify every candidate profile/adapter/environment cell as
  `supported`, `not_applicable`, `blocked`, or `deferred`, with stable reason
  codes and no implicit fallback to a different adapter or material set.
- [MUST] FR-003: Provide fake-only automated Fastmail and embedding fixture
  rows. Fastmail fixtures use synthetic de-identified messages and a controlled
  read-only `search_email` handler; embedding fixtures use sealed synthetic
  documents and an injected provider. Neither may access Fastmail, OAuth,
  network, model downloads, or a real mailbox.
- [MUST] FR-004: Provide an opt-in, redacted, read-only Fastmail live-probe
  route only for a cell classified `supported` and only after separate human
  authorization. It must not run from ordinary pytest or CI.
- [MUST] FR-005: Record a redacted receipt with profile ID, adapter/profile
  identity, capability decision, material-binding decision, test mode, terminal
  classification, dispatch count, and bounded diagnostics. It must retain no
  credential, mailbox content, raw tool result, prompt, or raw model output.
- [MUST] FR-006: Require each live or deterministic result to be tied to the
  exact sealed package/material descriptor it evaluated. A result for the
  current Qwen Fastmail package cannot establish support for another generator.
- [MUST] FR-007: Keep the current S1--S6 controlled tool-interface matrix and
  existing Fastmail acceptance independent; this feature composes their facts
  and adds workflow-level coverage rather than changing their contracts.
- [MUST] FR-008: Define initial profiles for synthetic Fastmail triage,
  synthetic embedding/index execution, sealed multimodal converter/generation,
  structured-output-after-tool-use, stateful context preparation, and injected
  tool-pack composition. Each profile must declare the exact workflow contract
  it covers and the capability facts it needs.
- [MUST] FR-009: The sealed multimodal converter/generation profile must bind
  the exact floorplan package/material/converter descriptors and separately
  represent deterministic fixture coverage from an operator-authorized MPS
  completion probe.
- [MUST] FR-010: Structured-output, stateful-context, and tool-pack-composition
  profiles must remain deterministic and injected. They must not call a remote
  model, external service, retrieval system, or subagent process.
- [MUST] FR-011: The Fastmail live probe must accept an explicit registered
  workflow ID and derive its static sealed package/material and policy facts
  from that registered host state before host composition. Its configured host
  must revalidate the dynamic reviewed MCP surface before tool dispatch. It
  must not use one operator argument as both a workflow registration ID and
  package ID, or accept operator-supplied support facts.
- [MUST] FR-012: An explicit owner-only reconciliation may refresh a stale
  workflow registration only when its workflow ID, package ID, and revision
  digest remain unchanged and the current configured profile and reviewed MCP
  binding revalidate. It must fail closed rather than replace an alias with a
  different package or revision.

## Non-Functional Requirements

- [MUST] NFR-001: Ordinary automated tests are deterministic, offline, and
  fake-backed.
- [MUST] NFR-002: The matrix must remain extensible by adding declarative
  profiles and capability facts, not provider-name special cases.
- [MUST] NFR-003: Unsupported and deferred rows must be visible in the report
  and must not count as passing evidence.

## WMS1 Classifier Contract

WMS1 is a pure, side-effect-free classification boundary. It receives only
immutable declarative values; it must not construct an adapter, load a package,
resolve a provider, read materials, import a model runtime, or dispatch a tool.
The existing `CapabilityStatusReport` remains a workflow-preflight input, not
the support-matrix result type.

A `WorkflowSupportProfile` has a stable profile ID, workflow family, sorted
required adapter, ABI, provider, and host capability facts, sorted required
material roles, execution mode, and authorization class. A profile digest is the
SHA-256 of its UTF-8 canonical JSON
representation: recursively NFC-normalized strings, object keys sorted, and JSON
encoded with `sort_keys=True`, `separators=(",", ":")`, and
`ensure_ascii=False`. A `WorkflowSupportCandidate` has an adapter identity,
adapter, available-ABI, host, and provider capability facts, and an optional material
identity. A material identity has a package ID, material-lock digest, and any
descriptor/converter digest declared by the profile. A candidate cannot claim
an identity by repository name, mutable revision label, path, or provider name.

A `WorkflowSupportCell` contains the profile digest, candidate identity,
one terminal status, and an ordered tuple of reason codes. A deterministic or
live `WorkflowSupportReceipt` repeats those values and binds them to its exact
test mode. A receipt is rejected when its profile digest, adapter identity,
package ID, material-lock digest, or any profile-required descriptor/converter
digest differs from the evaluated cell. WMS1 defines these data contracts and
their pure validation only; receipt rendering and live dispatch begin in WMS3.

The only WMS1 reason codes are:

| Code | Terminal status |
| --- | --- |
| `profile_unimplemented` | `deferred` |
| `adapter_capability_missing` | `not_applicable` |
| `required_material_missing` | `blocked` |
| `material_identity_mismatch` | `blocked` |
| `required_abi_unavailable` | `blocked` |
| `required_provider_unavailable` | `blocked` |
| `required_host_capability_missing` | `blocked` |
| `authorization_missing` | `blocked` |

Malformed profiles, candidates, or receipts are invalid inputs and raise before
classification; they are not a fifth status. For valid inputs, the classifier
uses this precedence: `profile_unimplemented`; then
`adapter_capability_missing`; then all applicable `blocked` reasons in lexical
code order; otherwise `supported` with no reasons. A supported cell has no
reason codes; every other cell has one or more codes allowed by its status.

## Acceptance Criteria

- AC-001: Given a Fastmail profile requiring tool use and a read-only tool
  surface, when an adapter lacks the required tool path, then the matrix emits
  `not_applicable` without constructing a model or dispatching a tool.
- AC-002: Given an embedding profile whose locked descriptor requires an ABI
  unavailable on the host, when it is evaluated, then the matrix emits
  `blocked` with a stable material/ABI reason and does not load a model.
- AC-003: Given an eligible synthetic Fastmail profile, when its automated row
  runs, then it produces the contract-valid triage result using only controlled
  data and exactly the permitted read-only dispatches.
- AC-004: Given a `supported` live Fastmail candidate and explicit operator
  authorization, when the probe completes, then it emits a redacted receipt;
  without authorization it does not start.
- AC-005: Given a result from a different package digest or material descriptor,
  when evidence is recorded, then the matrix rejects it as non-transferable.
- AC-006: Given a floorplan candidate missing its exact converter, material
  closure, eligible MPS policy, or required output validator, when evaluated,
  then it is non-executing and classified with the missing fact; given all
  facts and authorization, its manual completion receipt is descriptor-bound.
- AC-007: Given a structured-output-after-tool-use profile, when the controlled
  tool result is returned, then an eligible synthetic adapter produces only the
  declared schema-valid terminal result; a missing structured-output capability
  is `not_applicable` before model dispatch.
- AC-008: Given a stateful-context profile, when bounded prior turns, session
  state, and an overflow-retry fixture are prepared, then the matrix records
  the selected context and terminal classification without retaining raw turns.
- AC-009: Given a tool-pack-composition profile, when the controlled web,
  workspace, and subagent collaborators are injected, then descriptor packing,
  approval, invocation, and redacted result shaping are tested with no external
  client or child process.
- AC-010: Given a Fastmail registration whose workflow ID and package ID are
  distinct, when an explicitly authorized probe is evaluated, then it derives
  static package/material and policy facts from the registered immutable state.
  An unknown workflow or changed static fact refuses before host opening; a
  stale dynamic reviewed surface refuses before tool dispatch.
- AC-011: Given a stale Fastmail registration policy for the same cataloged
  package and revision, when an owner requests reconciliation and current
  profile/MCP binding revalidation succeeds, then the registration refreshes;
  a different package or revision is rejected without altering the alias.

## Edge and Error Cases

- An unregistered adapter, unavailable host capability, missing provider, or
  unprepared material closure is classified; it is not retried or downloaded.
- A matrix profile that conflicts with its sealed package contract is invalid
  and fails before execution.
- A live authorization rejection or expired reviewed tool surface is `blocked`;
  no tool dispatch occurs.

## Boundaries

- In scope: support classification, deterministic fixtures, redacted receipts,
  manual read-only Fastmail and floorplan gates, and documentation of coverage.
- Out of scope: making every adapter support tool use or embeddings; converting
  models; sharing model files across incompatible backends; changing Fastmail
  OAuth/MCP behavior; live mailbox mutation; automatic model provisioning; and
  CI live-model execution.
- Always do: preserve sealed material identity and fail closed at external
  boundaries.
- Ask first: each live Fastmail/MCP/OAuth dispatch.
- Never do: retain secrets, mailbox content, or raw model/tool content in a
  receipt.

## WMS3 Floorplan MPS Completion Probe Contract

WMS3.3 is one operator-gated live probe for the already registered
`floorplan-from-image` package. It must derive the live
`floorplan-svg-mps-completion-v1` profile and its `MaterialIdentity` from the
registered immutable revision and compiled policy; an operator must not supply
mutable profile, material, descriptor, converter, processor, or validator facts
in a support-facts file. The derived identity includes the execution descriptor,
input converter, JSON-admission processor, JSON-to-SVG renderer, and terminal
SVG validator digests.

The command requires an explicit opt-in environment variable, package name,
target label, authorization reference, state root, and receipt destination. It
classifies the derived MPS candidate before opening the host or creating a
generation worker. Only an exact `supported` live cell may dispatch one sealed
image. A missing authorization, MPS capability/policy, runner capability,
material role, or any identity mismatch is a zero-dispatch refusal.

The completion probe follows the selected M9.3 witness exactly: the model
result is admitted as complete floorplan JSON, then the package's sealed
workflow-local processor renders SVG, and the sealed validator accepts that SVG.
The probe rejects an admission, rendering, or SVG-validation failure without
publishing a receipt that claims completion.

Its fixed redacted receipt contains only: format version; profile ID and digest;
adapter ID; material identity; test mode; status/reason codes; dispatch count;
digests of target and authorization reference; execution-descriptor digest;
packed-context, aggregate-generated-token, and aggregate-output-byte scalars;
and a boolean worker-reaped attestation. It contains no image, prompt, model
JSON, SVG, paths, raw tool output, process identifier, credential, or memory
address. The generic generation-worker result must expose the scalar
worker-reaped attestation after confirmed cleanup so the probe does not inspect
worker internals.

## Dependencies and Assumptions

- Depends on `model-interface-parity`, `fastmail-inbox-triage`,
  `workflow-embedding-index-artifacts`, model-generation resource budgets,
  context preparation, tool-pack contracts, workflow capability requirements,
  and model-material binding/preparation contracts.
- Assumption: runtime capability reporting can expose enough adapter/provider
  facts to classify a candidate without starting a model. Any missing fact is
  `blocked` or `deferred`, never inferred.
