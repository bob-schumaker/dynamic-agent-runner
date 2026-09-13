# Natural-Language Workflow Authoring Specification

## Metadata

- Feature slug: `natural-language-workflow-authoring`
- Status: implemented through NLA-5
- Owner: dynamic-agent-runner
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Implementation plan: `plan.md`
- Task list: `tasks.md`
- Related specifications:
  - `specs/authored-workflow-runtime-v1/spec.md`
  - `specs/host-workflow-integration/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/local-tool-sandbox-hardening/spec.md`
  - `specs/model-adapter-coverage/spec.md`
  - `specs/workflow-input-converter-plugin/spec.md`

## Objective

Let a user describe a bounded DAR workflow in natural language and receive an
executable workflow when its declared runtime requirements already exist,
without learning DAR control-plane details. When a request needs a capability
or workflow-local tool that is not implemented, the authoring surface creates
repository-appropriate implementation guidance instead of pretending the
workflow is ready. It asks a follow-up only when a required workflow contract
cannot be determined from the request.

For example, this request:

> Design a DAR workflow that uses the qwen25-vl-3b-floorplan-grpo model with
> llama.cpp to accept an image and turn it into a floorplan.

requires one question because the output representation is under-specified:

> What output format should it produce?

Given `SVG`, the result is either a validated and saved workflow that accepts
one image and returns an SVG floorplan, or a concise implementation
specification for its missing image runtime capability or workflow-local SVG
validator. It is executable only after those requirements are implemented and
configured.

## Problem Statement

The current authoring path exposes implementation details that a normal user
cannot usefully act on: material manifests, absolute paths, `material_set_id`,
authoring-output IDs, package-finalization commands, and host receipts. Those
details are needed only to compose existing host controls; they are not part of
the user's workflow intent.

This feature replaces that user-facing ceremony with one task-oriented entry
point. It does not weaken validation, local-model eligibility checks, trusted
file ingress, package finalization, or registration binding.

## Scope

This feature covers Agent Engineering workflow design plus a host-owned
registration transaction for bounded DAR workflows. Its first vertical slice
is image-to-SVG generation with a workflow-local validator; an additive slice
covers tool-backed opaque-binary analysis. It:

1. derives a candidate workflow contract and identifies its implementation
   requirements from the user's request;
2. asks only for facts that cannot be inferred safely or deterministically;
3. writes a repository-appropriate implementation specification when a
   required DAR capability, workflow-local tool, or converter execution
   capability is absent;
4. creates and consumes private authoring materials and output handles inside
   the host only for a workflow whose requirements are already implemented;
5. validates, stages, registers, and saves that workflow; and
6. returns a concise user-facing registered workflow, implementation
   specification, or availability result.

When the workflow input converter plugin capability is implemented, authoring
may include one contract-conforming, workflow-sealed Python converter package.
That exception is limited to
`specs/workflow-input-converter-plugin/spec.md`; it does not authorize generic
local-tool code or host-wide executable installation.

The first vertical slice supports an image input artifact, an explicitly chosen
SVG output contract, and a workflow-local deterministic SVG validation tool. It
uses an already configured, image-capable llama.cpp model profile. It is
not ready until those generic runtime capabilities and the
workflow-local validator are implemented. Once they exist, a missing or
text-only configured profile is unavailable; it must not pretend that a
text-only profile can process an image.

The SVG validator is host post-processing, not a model-callable tool. After
terminal-output shaping, DAR may pass the bounded terminal message to one
workflow-declared local validator and accept only its bounded JSON validity
evidence. DAR does not parse SVG or otherwise interpret domain output; the
workflow-owned validator owns that semantic check. A failing validator yields
the workflow's declared redacted failure.

The opaque-binary analysis slice supports an already configured, reviewed tool
package. It lets that package, rather than the skill or DAR, determine which
binary encodings it can inspect.

## Non-Goals

This feature does not:

- start, download, discover, or configure llama.cpp or model files;
- create profiles, credentials, connections, MCP servers, or host-wide tools;
  a workflow may instead declare deterministic local tooling for DAR's approved
  sandbox runtime;
- add an interactive general-purpose agent or an unbounded authoring loop;
- expose state-root paths, manifests, opaque IDs, package paths, or raw
  host receipts to the user;
- infer a model, input type, tool, external destination, side effect, or output
  artifact representation when the request does not establish one. A request to
  examine or analyze an input with no output artifact or destination has the
  deterministic default of plain-text analysis; or
- make live model, network, or GUI calls in unit tests; controlled temporary
  filesystem fixtures are limited to sealed-ingress and sandbox-containment
  coverage and must not access a caller workspace or external tool.

## User-Facing Contract

### FR-1: Minimal clarification

The Agent Engineering `agent-development` skill shall extract the requested
task, named model and adapter, input kind, tool requirement, and output
contract from natural language. It shall ask no question when those values are
established.

When a required contract value has more than one material outcome, the skill
shall ask one direct question for that value and wait for the answer. It shall
not ask about package names, manifests, material sets, profile IDs, output
locations, or any other internal composition detail.

“Examine” or “analyze” with no requested output artifact or destination means
plain-text analysis and does not require an output-format question.

Acceptance criteria:

- The floorplan request above produces only the output-format question.
- Answering `SVG` produces an image-to-SVG floorplan design without further
  authoring questions. If a required runtime capability or local validator is
  absent, the design produces its implementation specification instead of a
  ready workflow.
- If a request explicitly says `return SVG`, it produces no clarification.
- A request that omits a required model, input kind, or output representation
  asks only the smallest question needed to resolve that omission.

### FR-2: Internal host composition

The façade shall use the existing authoring-material, package-output,
finalization, staging, validation, and registration boundaries internally. It
may issue `material_set_id` and authoring-output IDs, but those values must not
appear in prompts, responses, logs intended for users, or saved workflow
metadata.

Inline user intent is the authoring material for this flow. No manifest file or
human-selected material path is required when the request contains all required
design information.

Acceptance criteria:

- The complete floorplan flow has no user-visible manifest or opaque receipt.
- Internal finalization binds generated output to the internally issued authoring
  material set.
- A failed internal operation returns a stable, actionable user result and does
  not disclose a path, ID, credential, or source content.
- Existing direct host-control commands remain supported for callers that need
  explicit material selection.

### FR-3: Local-model eligibility and workflow creation

For a request that names a model and adapter and requires no unimplemented
workflow-local tool, the registration transaction shall select
only an already configured, eligible local profile whose adapter and model
identity match the requested values and whose declared capabilities include
`multimodal_input`. The profile's adapter or converter-backed runner must
transport the sealed image artifact to the model. It must not silently
substitute a model or hosted provider.

If no eligible profile exists, authoring ends with a concise availability result
that identifies the unavailable requested model capability without exposing
profile internals. It must not create a plausible package that cannot execute.

Acceptance criteria:

- A configured `qwen25-vl-3b-floorplan-grpo` llama.cpp profile produces a saved
  `floorplan-from-image` workflow (or a collision-safe generated equivalent).
- The workflow has one declared image input artifact, one declared
  workflow-local SVG validation tool, finite execution bounds, and one SVG
  terminal output.
- A missing, text-only, or incompatible local profile produces an unavailable
  result before package registration or model invocation.
- Existing profile-selection, model-coverage, and package-validation rules
  remain authoritative.

### FR-4: Executable handoff

On success, the façade shall return the saved workflow name, its input contract,
its output contract, and the command or host action for executing it. The result
must be sufficient for the user to run the workflow, but must not require the
user to handle an internal identifier.

For the SVG floorplan example, the result identifies that the workflow accepts
one image and returns SVG. Invocation continues to use trusted workspace input
ingress; a caller does not grant a model arbitrary filesystem access.

### FR-5: Stable façade protocol

DAR shall expose one skill-callable `register_authored_workflow` transaction.
Its internal input is the Agent Engineering skill's completed canonical
workflow contract plus a declarative workflow definition. Neither contains
executable local-tool code, a host path, profile ID, manifest, receipt, or
opaque handle. A converter-backed definition may additionally contain one
sealed converter package only when it satisfies the converter-plugin contract.
DAR validates the contract and definition,
then persists, stages, binds, registers, and selects it. DAR does not interpret
natural language or ask the user clarifying questions.

The DAR registration result is one of the following, and contains no internal
handles:

- `ready`: `workflow_name`, `input_contract`, `output_contract`, and an
  invocation action using the saved workflow name; or
- `unavailable`: the requested capability and one user-actionable requirement,
  such as configuring the exact named local model with image input support.

When a declared requirement has no implementation, Agent Engineering creates a
repository work-item specification naming the missing generic DAR slice or
workflow-local tool contract. It does not call
`register_authored_workflow` until that specification is implemented. This is
neither a DAR availability result nor a request for the user to configure
internals. Its user-facing presentation names what remains to be implemented
and the resulting workflow contract; it does not expose the status identifier,
host details, or control-plane steps.

That implementation specification shall state the workflow contract, the
missing capability or local-tool boundary, its sealed I/O and execution limits,
its declared failure result, and acceptance tests. It shall not include an
implementation, executable asset, generated source code, or an instruction for
the user to compose DAR control-plane values.

The Agent Engineering `agent-development` skill owns the user conversation:
it asks the minimum clarification, builds the canonical contract, determines
whether it has unmet implementation requirements, creates the corresponding
repository specification when needed, and otherwise calls the transaction. It
shall not generate executable local-tool code. Under the converter-plugin
contract, it may generate only a sealed contract-conforming Python converter
package for that transaction; it must not direct a
user to create a manifest, configure an authoring model, or provide a
`material_set_id`.

The `ready` SVG result shall identify one image input and an SVG output. The
workflow-local validator, not DAR, determines whether its terminal value is a
successful SVG result.

### FR-6: Deterministic authoring boundary

The authoring model may propose a declarative workflow definition and, only
under the workflow input converter plugin contract, its sealed converter asset.
The host remains the authority for schema validation, canonical package
artifacts, model-profile
binding, package naming collision handling, staging, registration, and saved
workflow selection. The authoring model cannot introduce tools, credentials,
external destinations, or side effects absent from the request and an existing
reviewed host capability. It may identify a deterministic local-tool
requirement only under the host's approved sandbox contract; it does not
implement that tool. A converter package is not a local tool and is permitted
only through the converter-plugin contract.

### FR-7: Tool-backed opaque-binary analysis

For this feature, a *tool package* is a host-owned, reviewed named collection:
a stable package name, an exact reviewed capability binding, and its allowlisted
tool descriptors. It is not a Python distribution, a user-provided path, or a
package that the authoring façade may discover or install.

For a request that names a tool package, the façade shall resolve only that
configured reviewed collection and its allowlisted tools. It shall model an
uploaded binary as one `opaque_binary_artifact`; the workflow and skill shall
not name or enumerate a binary encoding merely to create the workflow.

The selected tool receives the sealed artifact reference and bounded metadata,
never the caller's filesystem path or raw bytes in a model prompt. The tool
package owns format recognition and parsing, then returns bounded structured or
text evidence to the model. It may support PCAP, protobuf, or a future format
without a DAR or skill update.

If the named package is not configured and reviewed, or exposes no tool that
accepts an opaque binary artifact, authoring returns `unavailable` before
package registration. It shall not substitute another tool package or ask the
user to identify a binary format.

Acceptance criteria:

- “Create a workflow to examine network dumps for packet contents using the
  network tools in `<tool-analysis-package>`” produces a text-analysis
  candidate without a format clarification.
- The generated workflow declares one `opaque_binary_artifact` input, binds
  only tools from the named package, and applies declared tool and execution
  budgets.
- A binary-artifact-capable tool receives the sealed artifact reference and no
  original workspace path.
- A package that cannot accept an opaque binary artifact produces an unavailable
  result without creating a workflow.
- An unknown package name or a name that does not resolve to a current reviewed
  collection produces an unavailable result without fallback or package
  discovery.

## Prerequisite Slice: Multimodal Local-Profile Execution

The image-to-SVG vertical slice depends on this DAR runtime slice. Generic
trusted workspace ingress is already the binary-file boundary and remains
unchanged: it seals an accepted image artifact before workflow preparation. This
slice does not introduce an image-specific filesystem path, direct model file
access, or a second ingress mechanism.

The slice shall:

1. let an already configured local profile declare `multimodal_input` only when
   its exact adapter can accept sealed image artifacts;
2. derive registration capability resolution from that configured profile rather
   than the current fixed `text_generation` set;
3. transport a sealed image artifact, its approved media type, and no caller
   filesystem path to the selected llama.cpp adapter; and
4. reject preparation or execution when the artifact, media type, profile, or
   adapter capability does not match the registered workflow.

Acceptance criteria:

- A text-only llama.cpp profile cannot register or run an image-input workflow.
- An image-capable llama.cpp profile receives the sealed image artifact without
  receiving its original workspace path.
- Existing text-only workflows and generic workspace ingress behavior remain
  unchanged.
- Focused fake-only tests cover positive image transport and each rejected
  capability, media-type, and artifact-binding mismatch.

## Prerequisite Slice: Workflow-Local Deterministic Tooling

DAR shall provide a generic approved sandbox boundary for a workflow-declared,
deterministic local tool. The runtime owns tool identity, sealed inputs,
execution limits, result bounds, tracing, and failure containment. It does not
provide SVG, floorplan, PCAP, protobuf, or any other domain parser.

Agent Engineering may identify the need for a bounded local-tool contract, but
it does not author the asset or executable code. It creates a repository
implementation specification that states the required identity, sealed I/O,
limits, and declared failure contract. DAR admits an implementation only after
deterministic package validation and runs it only in the approved sandbox. It
must not execute model-generated host Python, grant ambient filesystem/network
access, or turn the tool into a host-wide installation.

Acceptance criteria:

- The floorplan implementation specification requires a local SVG validation
  tool; after it is implemented, DAR dispatches it through the generic sandbox
  without knowing SVG semantics.
- A failed validator produces the workflow's declared failure result without
  exposing sandbox paths, handles, or raw host errors.
- A tool that requests undeclared filesystem, network, process, or tool access
  is rejected before workflow registration.
- Existing no-tool and reviewed external-tool workflows remain unchanged.

## Additive Slice: Opaque-Binary Artifact Tool Analysis

This slice enables FR-7. It adds an `opaque_binary_artifact` workflow input
contract and an artifact-aware tool schema. The contract means only “a sealed,
bounded binary input”; it is not a DAR-maintained allowlist of formats or a
promise that every tool can decode every binary file.

The slice shall:

1. preserve generic trusted workspace ingress as the sole binary-file boundary;
2. add a host-owned named tool-package resolver that returns only a current
   reviewed capability binding and its allowlisted descriptors;
3. let those reviewed tool descriptors declare that they accept an opaque
   binary artifact reference without declaring a specific encoding;
4. pass the sealed reference and bounded host metadata only to those tools;
5. bind the resolved package identity and reviewed capability binding into the
   registered workflow, then enforce its declared tool allowlist, execution
   budgets, and result bounds; and
6. provide the model only bounded tool output, not raw binary bytes.

Acceptance criteria:

- A fake network-tool package can consume an opaque binary artifact and return
  bounded packet evidence without a model receiving the file bytes or path.
- A fake protobuf-capable package can use the same artifact contract without
  modifying the skill or DAR format registry.
- A non-artifact-aware tool cannot be bound to an opaque-binary workflow.
- An unknown, stale, or unreviewed tool-package name cannot resolve or fall back
  to another package.
- Existing no-tool workflows, text artifact behavior, and image ingress remain
  unchanged.

## Implementation Direction

Implement one narrow host service exposing `register_authored_workflow` and
make it the sole registration entry point used by `agent-development`. The
skill supplies
the canonical contract and declarative workflow definition only after all
implementation requirements are met. When they are not, it creates a
repository specification rather than a declarative definition containing code.
Existing
low-level commands remain private collaborators rather than becoming a second
skill-facing protocol. Existing direct control-plane commands keep their current
contracts for explicit callers.

Implement the prerequisite multimodal local-profile execution slice before the
façade's image-to-SVG success path. It is a DAR runtime change, not a profile
configuration task delegated to the user during authoring.

The skill's request-to-contract-and-requirements seam must be deterministic
enough for focused clarification tests without a live model call. Fixed
canonical contracts and declarative definitions replace the skill in host
tests; implementation-specification outcomes are tested at the skill boundary.

## TDD Implementation Tasks

1. Add failing Agent Engineering tests: the floorplan prompt produces only the
   output-format question, and `SVG` produces a repository implementation
   specification when its validator or image runtime is absent.
2. Add failing registration tests proving that a requirements-satisfied
   declarative definition is issued and finalized internally without
   user-visible manifests, paths, or opaque IDs.
3. Add failing multimodal prerequisite-slice tests for profile-derived
   `multimodal_input` capability and text-workflow compatibility.
4. Add failing profile-resolution tests for exact llama.cpp/model matching,
   unavailable failure, and no hosted or alternate-model fallback.
5. Add failing adapter and registration tests proving that a sealed image
   artifact reaches only an image-capable configured adapter and that a
   text-only profile cannot register the image workflow.
6. Add failing end-to-end fake-host tests that register and invoke the
   image-to-SVG workflow through trusted image ingress after its local validator
   implementation is present, including valid-SVG success and invalid-SVG
   failure.
7. Implement the smallest host service, capability binding, image transport,
   generic sandbox dispatch, and result schema that make those tests pass.
8. Update `agent-development` to create implementation guidance for unmet
   requirements, use `register_authored_workflow` only for
   requirements-satisfied designs,
   and never ask for a manifest or `material_set_id`.
9. Add failing opaque-binary slice tests for exact reviewed tool-package
   resolution, artifact-aware tool binding, sealed-reference-only invocation,
   bounded tool evidence, and unavailable package or capability results.
10. Add redaction regression tests for every user-facing success and failure
    payload.

## Validation

- Focused fake-only unit tests cover the skill's one-question clarification and
  implementation specification, registration receipt redaction, exact
  profile matching, multimodal capability binding, sealed image transport,
  declarative workflow validation, registration, workflow-local SVG validation,
  image-artifact invocation, opaque-binary artifact tool binding, and bounded
  tool evidence.
- Existing authored-workflow, host CLI, sandbox ingress, and model-profile tests
  continue to pass.
- A manual local acceptance run with an already configured
  `qwen25-vl-3b-floorplan-grpo` llama.cpp profile verifies that a supplied image
  yields syntactically valid SVG. This is separate from ordinary unit tests.
