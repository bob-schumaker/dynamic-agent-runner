# Workflow Model Support Matrix Specification

Status: Draft
Version: 0.1.0
Owner: Repository maintainers
Date: 2026-09-13

## Objective

Provide a single, capability-gated support matrix for DAR's Fastmail-triage and
embedding/index workflow families. It must make evidence and eligibility
auditable without claiming that a workflow is portable to a model or provider
that lacks its required capabilities or locked materials.

## User Stories

- As a maintainer, I want deterministic support rows for every registered
  workflow profile and model adapter so that unsupported combinations are not
  mistaken for regressions.
- As an operator, I want a redacted eligibility receipt before a live Fastmail
  run so that live authorization remains separate from ordinary tests.
- As a package author, I want embedding support evaluated against the workflow's
  locked material closure and ABI, rather than against a named global model list.

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

## Non-Functional Requirements

- [MUST] NFR-001: Ordinary automated tests are deterministic, offline, and
  fake-backed.
- [MUST] NFR-002: The matrix must remain extensible by adding declarative
  profiles and capability facts, not provider-name special cases.
- [MUST] NFR-003: Unsupported and deferred rows must be visible in the report
  and must not count as passing evidence.

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

## Edge and Error Cases

- An unregistered adapter, unavailable host capability, missing provider, or
  unprepared material closure is classified; it is not retried or downloaded.
- A matrix profile that conflicts with its sealed package contract is invalid
  and fails before execution.
- A live authorization rejection or expired reviewed tool surface is `blocked`;
  no tool dispatch occurs.

## Boundaries

- In scope: support classification, deterministic fixtures, redacted receipts,
  manual read-only Fastmail gates, and documentation of coverage.
- Out of scope: making every adapter support tool use or embeddings; converting
  models; sharing model files across incompatible backends; changing Fastmail
  OAuth/MCP behavior; live mailbox mutation; automatic model provisioning; and
  CI live-model execution.
- Always do: preserve sealed material identity and fail closed at external
  boundaries.
- Ask first: each live Fastmail/MCP/OAuth dispatch.
- Never do: retain secrets, mailbox content, or raw model/tool content in a
  receipt.

## Dependencies and Assumptions

- Depends on `model-interface-parity`, `fastmail-inbox-triage`,
  `workflow-embedding-index-artifacts`, workflow capability requirements, and
  model-material binding/preparation contracts.
- Assumption: runtime capability reporting can expose enough adapter/provider
  facts to classify a candidate without starting a model. Any missing fact is
  `blocked` or `deferred`, never inferred.
