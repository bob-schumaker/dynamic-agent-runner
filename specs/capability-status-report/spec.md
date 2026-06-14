# Capability Status Report Specification

## Metadata

- Feature slug: `capability-status-report`
- Mode: `light`
- Artifact type: future feature specification
- Status: proposed future usefulness feature; no implementation started
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related runtime surfaces:
  - runtime manifest metadata preservation
  - execution plan preparation
  - tool registry and tool provenance
  - model adapter coverage
  - built-in tool packs
  - lifecycle hooks and trace metadata

## Objective

Define a public capability/status reporting surface that tells callers which
workflow features are live, which are metadata-only, which require caller-supplied
runtime collaborators, and which are unavailable before execution starts.

This feature exists to make the package honest and usable as the specification
set grows. Manifest metadata must not be mistaken for live behavior.

## Problem Statement

The current specs intentionally preserve several future-facing metadata seams
before implementing the corresponding live runtime behavior. Examples include
approval interruption, async session continuity, sandbox/workspace runtime, MCP
registry sources, guardrail declarations, skill source resolution, and iterative
tool-use completion.

That is a good architecture pattern, but it creates a product risk: users can see
declared fields and assume behavior exists. A caller needs a simple way to ask:

- what can this package actually do now?
- what does this package only preserve as metadata?
- what would become live if I supplied a registry, adapter, source, grant, or
  policy?
- which workflow requirements will fail before execution?

Without a status report, the most accurate answer is spread across specs,
validation errors, and runtime behavior. That is too much work for a library
user.

## Scope

This feature covers:

1. a public report object for effective runtime capabilities
2. capability states such as live, metadata-only, missing collaborator, disabled,
   unsupported, and invalid
3. preflight inspection from a package directory plus caller-provided runtime
   collaborators
4. diagnostics for feature declarations that will not execute live
5. redacted reporting suitable for logs, CLI output, and tests

This feature does not cover:

1. implementing any missing live feature
2. enabling metadata-only features automatically
3. replacing existing manifest validation
4. exposing secrets, raw tool outputs, or full prompt bodies
5. introducing a UI

## Functional Requirements

### FR-1: Report effective capability states

The package must expose a repository-owned status shape that classifies relevant
features before execution.

Acceptance criteria:

- Given a workflow package declares only currently supported finite graph
  execution features, when status is requested, then those capabilities are
  reported as live.
- Given a workflow package declares deferred metadata such as guardrails,
  approval interruption, sandbox runtime, MCP sources, async sessions, skill
  refs, or loop completion policy, when the corresponding live runtime feature is
  not implemented, then the report marks it as metadata-only rather than live.
- Given a live-capable feature needs a caller-supplied collaborator, when that
  collaborator is missing, then the report marks the feature as missing a
  collaborator and names the collaborator type.
- Given a feature is disabled by caller policy, when status is requested, then
  the report distinguishes disabled from unsupported.

### FR-2: Preserve validation authority

Capability reporting must compose with existing validation instead of replacing
it.

Acceptance criteria:

- Given manifest validation fails, when status is requested in strict mode, then
  the report includes the validation failure and execution remains blocked.
- Given callers request advisory status, when a metadata-only feature is present,
  then reporting can explain the deferred behavior without treating the manifest
  as invalid.
- Given a package has missing required artifacts, then status reporting must not
  claim partial live support that execution cannot reach.

### FR-3: Include runtime collaborator diagnostics

The report must account for caller-supplied runtime collaborators.

Acceptance criteria:

- Model adapter coverage reports whether selected workflow models are covered by
  supplied adapters, augmented default OpenAI behavior, or neither.
- Tool capabilities report declared tools, registered callables, tool exposure
  states, provenance, side-effect metadata, and missing required tools.
- Built-in tool packs report whether they are disabled, enabled, or unavailable.
- Future collaborator types such as guardrail registries, interpreter registries,
  MCP sources, sandbox adapters, approval engines, and session stores can be
  reported without changing the basic status model.

### FR-4: Make metadata-only behavior explicit in user-facing output

Status output must prevent false confidence.

Acceptance criteria:

- The report has a summary that separates live, metadata-only, unavailable, and
  invalid capability counts.
- Each metadata-only item includes a short explanation that the runtime preserves
  or validates declarations but does not execute the behavior.
- The CLI, if it exposes this report, must avoid wording such as "enabled" for
  metadata-only features.
- The report can identify the owning spec slug or section for follow-up without
  embedding long prose.

### FR-5: Keep reporting deterministic and redacted

Capability status must be safe to use in tests and logs.

Acceptance criteria:

- Report ordering is deterministic.
- Sensitive values such as API keys, tokens, absolute secret paths, raw tool
  arguments, raw model output, and full prompt content are omitted or redacted by
  default.
- Unit tests can construct reports with fake packages, fake registries, fake
  adapters, and no live network or model calls.

## Suggested Public API Shape

The exact names are not authoritative. A future implementation may expose a
small API such as:

```python
from dynamic_agent_runner import inspect_agent_package_capabilities

report = inspect_agent_package_capabilities(
    package_directory="path/to/agent-package",
    tool_registry=registry,
    model_adapter=[adapter],
    model_adapter_coverage="strict",
)
```

The report should be structured enough for tests and simple enough for CLI
display. It should not require workflow execution.

## Design Constraints

- Keep this feature read-only.
- Do not mutate generated package artifacts.
- Do not make future metadata features live by reporting them.
- Reuse existing validation, preparation, registry, and model-selection helpers
  where possible.
- Keep detailed feature logic in owning feature specs; this spec owns the common
  reporting surface.

## Relationship to Council Recommendations

The council review recommended this feature because the spec set now contains a
wide gap between implemented runtime behavior and future metadata. This report is
the smallest product-facing way to keep that boundary visible while deeper live
features are implemented in separate slices.

## NEEDS CLARIFICATION

- Should the first public entry point live at package root, lower-level executor
  APIs, CLI, or all three?
- Should status reporting run full package preparation or a lighter validation
  path?
- What exact enum values should represent capability state?
- Should metadata-only declarations be warnings, informational diagnostics, or a
  separate report section?
- How should report output reference owning specs without coupling runtime code
  to repository-local spec paths?
- Should the CLI expose this as `validate --capabilities`, a new `inspect`
  command, or an option on the existing command?

## Validation Checklist

- [ ] Metadata-only approval, sandbox, MCP, guardrail, skill, loop, and session
      declarations are reported as metadata-only when live behavior is absent.
- [ ] Missing model coverage is reported consistently with
      `model_adapter_coverage`.
- [ ] Missing registered tools are reported without invoking tools.
- [ ] Enabled built-in read-only tool packs are distinguished from disabled packs.
- [ ] Report output is deterministic and redacted.
- [ ] Invalid package artifacts still fail closed.
