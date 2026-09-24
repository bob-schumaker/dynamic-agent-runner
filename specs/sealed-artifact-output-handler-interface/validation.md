# Sealed Artifact Output Handler Interface Validation

Status: implementation-ready

## Review scope

This review covered `spec.md` and the existing
`SealedArtifactOutputHandleService` seams that it names. No runtime code was
changed by this review.

## Council deliberation

Ada, Feynman, and Torvalds independently reviewed the lifecycle, replay,
expiry, ownership, and migration boundaries. Their material findings were
resolved by making `stage_declared` the v1 seam, defining concrete value
types, specifying promote/discard linearization, making private-set replay
identity normative, defining strict expiry, and adding stable error mapping
and precedence. The review also confirmed that workflow/package/producer
admission belongs to the handler rather than the storage service.

Council conclusion: **approved for implementation handoff**.

## Ponytail review

Ponytail review reduced the design to a four-operation adapter over the
existing service. It rejected a second store, registry, event bus, producer
abstraction, streaming surface, and provider-specific methods. The existing
`stage` and `publish` methods remain compatibility conveniences while
`stage_declared` is the canonical v1 seam.

Ponytail conclusion: **lean enough to execute**.

## Verification

- CodeGraph/source review confirmed the current service methods and affected
  callers before the contract was amended.
- `git diff --check` passes.
- The readiness gate in `spec.md` requires TDD-first deterministic tests for
  lifecycle, linearization, expiry, replay, error mapping, redaction, and
  unchanged legacy callers before implementation is declared complete.

This specification is ready to execute under its stated gates.

## Plan readiness review

The implementation plan was reviewed against the approved specification and
the current repository seams.

### Council deliberation

Ada, Feynman, and Torvalds independently reviewed the plan. The first pass
identified four material gaps: adapter-only normalization could not safely
prove discard/promote linearization, the private-ID serialization wording
contradicted the spec, the multimodal source anchor was wrong, and the
multimodal prerequisite was not an executable gate.

The amended plan resolves those gaps by naming a service-owned atomic terminal
outcome seam and transition table, limiting `private_set_id` to the
host-private lifecycle, anchoring the adapter at
`workflow_host/sealed_artifact_output_handler.py` and the migration at
`LocalWorkflowHost.dispatch_multimodal_runner`, and requiring the focused
multimodal protocol test command before migration edits.

Council conclusion: **approved for task-list authoring**.

### Ponytail review

Ponytail review found no requirement to delete. The plan keeps the smallest
viable four-operation adapter and reuses the existing service/store. The
service-owned terminal seam is the minimum needed to make the approved
discard/replay contract correct under concurrency; no registry, event bus,
second store, provider abstraction, or streaming surface was added.

Ponytail conclusion: **lean enough to proceed to task-list authoring**.

### Plan verification

- CodeGraph confirmed the current service symbols, affected callers, and
  multimodal host dispatch seam before amendment.
- `git diff --check` passes.
- The plan requires TDD-first RED tests, exact source/test anchors, focused
  verification commands, and a final compatibility gate.

The plan is ready for task-list authoring under its stated gates.

## Task-list readiness review

The task list was reviewed against the implementation-ready specification and
the reviewed plan.

### Council deliberation

Ada, Feynman, and Torvalds found the dependency chain and TDD sequence sound.
The review required tighter handoff evidence for the lifecycle seam, exact RED
commands, declaration resolution, and the existing multimodal publication
callback. The task list now freezes the private declaration resolver,
`_transition_private_output(...)->SealedArtifactPrivateTransitionResult`, the
handler-specific versus legacy discard boundary, exact lifecycle selectors,
and the completed-only `publish_result` callback gate.

Council conclusion: **approved for implementation handoff**.

### Ponytail review

Ponytail review found no task to delete. The list keeps one adapter, one
existing state authority, and one migration callback seam. The additional
service transition result is limited to the concurrency contract already
required by the specification; no second store, registry, event bus, or
provider abstraction was introduced.

Ponytail conclusion: **lean enough to execute**.

### Task verification

- Current service and host symbols were confirmed with CodeGraph and targeted
  source inspection.
- `git diff --check` passes.
- Every implementation task has a preceding RED task, and every final gate
  names a focused command plus the full regression command.

The task list is ready for implementation handoff under its stated gates.

## Implementation evidence

- Added `src/dynamic_agent_runner/workflow_host/sealed_artifact_output_handler.py`
  with immutable request/read-binding values, host-owned declaration resolution,
  four handler operations, and redacted error mapping.
- Added the handler-specific atomic `transition_private_output` seam while
  preserving legacy public `discard` behavior.
- Added focused contract, lifecycle, replay, expiry, redaction, and concurrent
  promote/discard tests in `tests/test_sealed_artifact_output_handler.py`.
- The focused sealed-output, workflow-host, reviewed-capability, and multimodal
  suites pass together: **77 passed**.
- The existing multimodal host callback remains completed-only; repository
  inspection found no production callback carrying private output candidates,
  so no speculative publication path was introduced.
- `poetry run pytest -q`: **2800 passed, 1 skipped, 7 deselected**.
- `poetry run ruff check src tests`: pass.
- `git diff --check`: pass.

Implementation tasks are complete under the discovered repository boundary.
