# Hash-Chained Governance Audit Specification

## Metadata

- Feature slug: `hash-chained-governance-audit`
- Mode: `light`
- Artifact type: future feature specification
- Status: future investigation; not implementation authorization
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related specs:
  - `specs/approval-interruption-resume/spec.md`
  - `specs/live-guardrail-execution/spec.md`
  - `specs/model-event-streaming/spec.md`
  - `specs/persistent-agent-sessions/spec.md`
- Evaluated supporting reference:
  - `https://github.com/MARKTECHPOST-AI-MEDIA-INC/AI-Agents-Projects-Tutorials`
  - `Agentic AI Codes/microsoft_agent_governance_toolkit_policy_controls_tutorial_marktechpost.py`

## Objective

Define an optional, caller-sink-backed governance record stream whose records
form a verifiable hash chain. The feature should make deletion, insertion,
reordering, and modification detectable while preserving DAR's existing
approval, guardrail, trace, session, and caller-owned persistence boundaries.

The hash chain is tamper-evident, not tamper-proof. Without an external trust
anchor or signature it cannot prove who wrote a record, prevent an authorized
store operator from replacing the entire chain, or provide non-repudiation.

## Problem Statement

DAR can emit redacted trace events and approval interruptions, but ordinary
event records do not prove that an exported governance history remains in its
original order and form. High-risk tool workflows may need an independently
verifiable record of policy evaluations, approvals, invocation boundaries, and
outcomes without placing raw sensitive arguments in an audit store.

The evaluated MarkTechPost governance tutorial demonstrates a useful minimal
shape: decision identifiers, policy and rule identity, severity, approver,
previous-record hash, record hash, and whole-chain verification. Its
process-local list, simulated approval callback, and unkeyed payload hashing are
educational examples rather than a production persistence or identity model.

## Ownership Boundary

This feature owns:

1. a versioned governance-record schema
2. deterministic canonicalization and record hashing
3. previous-record linkage, sequence rules, and genesis semantics
4. append and verification collaborator contracts
5. redaction and invocation-fingerprint requirements
6. capability/status and failure reporting for configured audit behavior

This feature does not own:

- whether an action is approved or rejected
- policy or guardrail evaluation logic
- trace delivery, user-facing event streaming, or approval UI
- durable session or workflow checkpoint storage
- a database, ledger service, key-management service, or remote audit backend
- legal compliance certification, signatures, or non-repudiation

Approval remains owned by `approval-interruption-resume`; guardrail decisions
remain owned by `live-guardrail-execution`; ordinary observability remains in
the trace surface; persistence remains caller supplied.

## Proposed Record Contract

Each record should contain:

- `schema_version`
- `stream_id`, `record_id`, and monotonic `sequence`
- `recorded_at` in a normalized UTC representation
- `event_type` and outcome state
- run, workflow, session, node, tool-call, and trace correlation ids when present
- subject/action identity, including final tool id for invocation records
- policy id, policy version, rule id, severity, and reason code when present
- approval decision id, approver identity/source, and approval state when present
- a fingerprint of the final normalized invocation when the record concerns a
  tool action
- redaction profile and canonical payload digest metadata
- `previous_hash`, `record_hash`, and `hash_algorithm`

Optional fields must have deterministic absent/null treatment. Unknown fields
must either be included in canonicalization or rejected according to schema
version policy; silently dropping them would make verification ambiguous.

## Canonicalization and Hashing

- Records use a deterministic, versioned canonical byte representation.
- The record hash covers a domain separator, schema version, hash algorithm,
  stream id, sequence, previous hash, and canonical redacted payload.
- The first record uses an explicit versioned genesis marker, not an empty value
  whose meaning can vary by implementation.
- One stream uses one declared hash algorithm unless a versioned rotation record
  links the old and new algorithm segments.
- Verification recomputes every record hash and checks stream identity,
  contiguous sequence, previous-hash linkage, canonicalization version, and
  genesis/rotation rules.
- Unsupported algorithms or schema versions fail verification clearly.

The exact canonical JSON profile and initial hash algorithm remain an
implementation-plan decision. The plan must use a standard deterministic
serialization rather than relying on Python dictionary insertion order or
default `json.dumps(...)` behavior.

## Invocation Fingerprints and Privacy

Approval and invocation records must refer to the same final normalized
invocation envelope defined by `approval-interruption-resume`.

- A fingerprint binds the effective tool id, policy identity, schema identity,
  and final schema-valid arguments.
- A changed tool id or argument set creates a different fingerprint and requires
  revalidation and reauthorization before invocation.
- Raw secrets, prompts, tool arguments, and tool results are excluded from the
  default governance record.
- A plain hash of low-entropy sensitive values can leak equality or permit a
  dictionary attack. Callers exporting sensitive fingerprints must be able to
  supply a keyed fingerprint strategy or a redacted projection.
- Key identifiers may be recorded; secret keys must never enter workflow
  packages, trace payloads, governance records, or serialized resume state.

## Append and Concurrency Semantics

The caller supplies an append/verify collaborator. DAR must not silently fall
back to an in-memory or local-file ledger when governance audit is required.

- Append is compare-and-append against the expected previous hash and sequence.
- Concurrent writers either serialize through the caller's sink or receive a
  conflict and retry from the newly observed head.
- A fork, duplicate sequence, or unexpected head is an integrity conflict, not
  a valid second history.
- Record ids are idempotency keys. Repeating the same append may return the
  existing identical record; the same id with different content fails.
- Export and verification APIs operate on caller-supplied records and do not
  require the original live runtime collaborators.

## Event Boundary

Future implementation may record these governance events:

- policy or guardrail evaluated
- approval requested, approved, rejected, expired, or cancelled
- governed invocation prepared
- invocation started, completed, failed, timed out, or cancelled
- integrity conflict or audit append failure
- hash algorithm or schema rotation

Governance events are a strict, stable subset derived from runtime decisions;
they are not a copy of every trace or streaming event. Replayed streaming events
must never append duplicate governance records.

## Failure Policy

Configuration distinguishes `required` from `best_effort` audit behavior.

- In `required` mode, failure to append the pre-side-effect governance record
  fails closed before invoking the governed action.
- A failure to append an outcome record after a side effect cannot undo the
  action. The runtime returns an explicit incomplete-audit error containing
  safe reconciliation identifiers and must not report fully audited success.
- In `best_effort` mode, append failures are surfaced through redacted status and
  trace diagnostics; they are never silently ignored.
- Verification failure never rewrites or repairs records automatically.

## Functional Requirements

### FR-1: Produce deterministic records

Given identical schema-valid governance input and the same chain head, two
conforming implementations must produce the same canonical bytes and record
hash.

### FR-2: Detect history mutation

Verification must detect modified payloads, deleted records, inserted records,
reordered records, broken previous-hash links, duplicate or skipped sequences,
invalid genesis records, and unsupported rotations.

### FR-3: Bind authorization to execution

For a governed tool action, approval, prepared-invocation, and invocation-start
records must carry the same final invocation fingerprint. A mismatch fails
closed before the handler is invoked.

### FR-4: Preserve sensitive-data boundaries

Default records contain identifiers, decisions, reason codes, bounded metadata,
and protected fingerprints rather than raw arguments or results. Redaction is
applied before canonicalization so verification does not require secret data.

### FR-5: Remain caller-storage neutral

DAR exposes record construction, append, head lookup, and verification
contracts without bundling a durable store. Fake in-memory collaborators cover
unit tests; production persistence remains caller supplied.

### FR-6: Report capability honestly

Capability/status distinguishes disabled, metadata-only, live, missing sink,
degraded append, integrity conflict, unsupported schema/algorithm, and invalid
configuration states.

## Non-Goals

- No blockchain, consensus protocol, distributed ledger, or cryptocurrency.
- No claim that a bare hash chain authenticates the writer.
- No default storage of raw prompts, arguments, results, or secrets.
- No automatic policy decision, approval, or rejection.
- No attempt to make arbitrary trace streams hash chained.
- No implementation based only on the tutorial's process-global list.

## Initial Release Boundary

If scheduled, the first release should include only:

1. versioned record and verification result dataclasses
2. one deterministic canonicalization profile and one hash algorithm
3. genesis, append, idempotency, and sequential verification behavior
4. a caller-supplied sink protocol with a fake in-memory test implementation
5. final-invocation fingerprint binding for approval and tool-start records
6. required versus best-effort failure policy
7. redacted trace and capability/status diagnostics

Algorithm rotation, signatures, external anchoring, batch/Merkle proofs, remote
stores, retention policy, and compliance exports remain future work.

## Acceptance Criteria

- Unit tests first demonstrate that mutation, deletion, insertion, reordering,
  duplicate sequence, and broken linkage fail verification.
- Unit tests first demonstrate deterministic hashes for fixed canonicalization
  vectors and reject unsupported schema or algorithm versions.
- An approval followed by unchanged invocation produces matching fingerprints;
  post-approval argument replacement fails before tool invocation.
- Required-mode append failure prevents a pre-side-effect tool action.
- Post-side-effect outcome append failure produces an explicit incomplete-audit
  result and reconciliation identifiers.
- Default records and diagnostics contain no raw tool arguments or results.
- Tests use fake sinks, fake tools, and fake model adapters; no live services or
  model calls are required.

## Open Questions

- Which standard canonical JSON profile should v1 adopt?
- Should v1 use an unkeyed digest only for non-sensitive canonical payloads and
  require caller-supplied HMAC for protected invocation fingerprints?
- What external anchor or signature contract, if any, is worth a later feature?
- Should one chain span a run, session, workflow package, tenant, or
  caller-defined governance stream?
- What retention and export formats are required by the first concrete caller?

## Validation Checklist

- [ ] Fixed canonicalization vectors produce stable hashes.
- [ ] All specified chain mutations are detected.
- [ ] Concurrent compare-and-append conflicts fail deterministically.
- [ ] Invocation fingerprints bind final approved arguments.
- [ ] Required-mode pre-action append failures fail closed.
- [ ] Outcome append failures are distinguishable from tool failures.
- [ ] Default records and diagnostics pass sensitive-field inspection.
- [ ] Capability/status covers every declared state.
