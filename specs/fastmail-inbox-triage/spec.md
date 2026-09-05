# Fastmail Inbox Triage Specification

## Metadata

- Feature slug: `fastmail-inbox-triage`
- Mode: `guided`
- Artifact type: feature specification
- Status: implemented and accepted through v4
- Version: `0.1.0`
- Date: 2026-09-02
- Owner: dynamic-agent-runner
- Discovery: [`discovery.md`](discovery.md)
- Decision record: [`decision-log.md`](decision-log.md)
- Prerequisites:
  - `specs/authored-workflow-runtime-v1/spec.md`
  - `specs/mcp-oauth-discovery-registration/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/local-model-availability-api/a5.2-copy-receipt.md`
  - `tasks.md`
  - `validation.md`

## Objective

Deliver a saved DAR workflow that lets the account owner triage a small, recent
set of unread Fastmail messages with the downloaded llama.cpp-compatible
`Qwen/Qwen2.5-3B-Instruct-GGUF` model.
It returns a structured report and optional reply text without changing the
mailbox or sending any message.

## Readiness Gate

This is a host-constrained classification transaction, not a mailbox agent.
No package may be authored, registered, or invoked until P0 records an
explicitly authorized local-only qualification of the exact model artifact and
llama.cpp configuration. P0 uses synthetic data only and constructs no MCP
client or network connection.

## Problem statement

The owner needs a privacy-preserving way to identify recent messages that merit
attention without giving a local model a general-purpose mailbox-management
console. The existing Fastmail OAuth and read-only acceptance path proves the
host integration boundary, but it does not define a reusable user-facing inbox
triage workflow.

## Users

- Account owner, who reads the report and decides whether to take a later,
  separately authorized action.
- Host administrator, who configures the MCP connection, reviews its current
  surface, verifies the bound local model, and registers the saved package.

## User stories

- As an account owner, I want a bounded report of my recent unread messages so
  that I can decide what deserves attention without granting mailbox-write
  authority to the model.
- As a host administrator, I want the saved workflow bound to a current
  reviewed Fastmail surface and explicit local model binding so that a stale
  connection or broad tool list cannot change its authority.

## Scope

The workflow processes at most five unread messages received during the 24
hours preceding invocation. It may make at most one call to the host-bound,
current reviewed `search_email` tool and returns terminal text/structured data.

The package may use only the direct in-process llama.cpp adapter bound to
`Qwen/Qwen2.5-3B-Instruct-GGUF` revision
`7dabda4d13d513e3e842b20f0d435c732f172cbe` and file
`qwen2.5-3b-instruct-q4_k_m.gguf`, plus the one reviewed semantic read tool.
It must not assume a remote tool name, raw schema, response fields, endpoint,
OAuth scope, token, or connection identifier inside package artifacts or
model-visible input.

Before model load, the host verifies the recorded SHA-256, one immutable model
alias, `HuggingFaceModelFileReference(repo_id, filename, revision)`,
`allow_network=False`, expected identity, strict coverage, and a persisted
llama.cpp configuration fingerprint. The fingerprint includes `chat_format`,
tool codec, context limit, and generation parameters. P0 approved
`chatml-function-calling` for the recorded configuration fingerprint after its
local-only synthetic qualification.

## Functional requirements

### [MUST] FR-001: Host-owned Fastmail readiness

Before a run, the DAR host must revalidate the configured Fastmail connection's
current reviewed MCP surface and bind the package only when the approved
`search_email` semantic capability remains available with its reviewed identity
and input schema.

Acceptance criteria:

- Given an authenticated Fastmail connection and unchanged reviewed surface,
  when the host prepares a run, then it may bind only the approved
  `search_email` capability.
- Given missing authentication, metadata drift, reviewed-surface drift, a
  missing capability, or schema/identity mismatch, when preparation runs, then
  it fails before model invocation and remote dispatch with a stable redacted
  status.
- Given a broader Fastmail surface, when the package runs, then no other tool
  is exposed to the model or dispatched.

### [MUST] FR-002: Strict llama.cpp Qwen binding

The workflow must run only with the downloaded Qwen2.5 GGUF through the direct
in-process llama.cpp adapter and strict adapter coverage. It must not fall back
to an HTTP model, another local adapter, another Qwen artifact, or an
unconfigured alias.

Acceptance criteria:

- Given the configured Qwen GGUF is available, when the host starts the
  workflow, then it constructs the matching llama.cpp adapter from the
  configured alias only.
- Given the model file, immutable revision, or expected model identity is
  unavailable or does not match the saved registration,
  when preparation runs, then the host fails before consuming mailbox data,
  model generation, or MCP dispatch.

### [MUST] FR-003: Bounded read-only query

The workflow must request at most five unread messages from the preceding 24
hours through the one bound read-only capability. It must make no more than one
remote tool call during a run.

The model receives a zero-argument semantic `search_email` wrapper only. DAR
rejects every model argument; after current reviewed-surface validation, the
host alone maps it to Fastmail with `unread=true`, an invocation-minus-24-hour
lower bound, and `max_results=5`. Control-plane tools/schema checks are not
mailbox dispatch. Only a bounded, attachment-free result projection reaches the
model or traces.

Acceptance criteria:

- Given matching unread messages, when the model uses the bound tool, then the
  host enforces a single dispatch and a result limit of five messages.
- Given more than five matching messages, when the report is returned, then it
  indicates that the result is truncated rather than implying the mailbox was
  fully triaged.
- Given an empty result, when execution completes, then the report states that
  no matching messages were returned.
- Given a tool timeout, malformed result, or indeterminate outcome, when the
  run ends, then it returns a redacted failure or `needs_review` result and
  does not issue an automatic second remote call.
- Given the initial model turn, it either emits exactly one zero-argument
  `search_email` call or ends without dispatch. After dispatch DAR continues
  once with tools disabled; further calls or invalid call JSON fail without
  dispatch.

### [MUST] FR-004: Structured triage report

The terminal result must be structured and contain a per-message triage
classification of `urgent`, `needs_reply`, `fyi`, or `needs_review`. It may
include a concise rationale and proposed reply text, but proposed text is not a
message creation or dispatch instruction.

Acceptance criteria:

- Given data sufficient for classification, when the local model completes,
  then every returned message has exactly one classification and concise
  rationale.
- Given missing, ambiguous, or contradictory message data, when the model
  completes, then it classifies the message as `needs_review`.
- Given the Fastmail model returns JSON that is not a valid triage report, when
  the host processes terminal output, then it rejects the run rather than
  returning raw projected mailbox fields as a completed report.
- Given an otherwise-valid triage item repeats the bounded projection's
  `sender`, `received_at`, or `preview` field, when the host processes terminal
  output, then it removes only those fields before strict report validation and
  return; unknown fields and invalid statuses still fail closed.
- Given a request for a reply, when the result includes reply text, then the
  result labels it as an unapproved proposal and contains no action field,
  recipient, draft, or invocable send/reply instruction.
- Given a message reference appears in the report, when a later workflow uses
  it, then it is a user-visible reference only and supplies no authority for a
  side-effecting operation.
- Given terminal model output, DAR parses and validates the report contract:
  known classifications, opaque returned references only, at most five items,
  and consistent count/truncation. Invalid output returns redacted
  `needs_review` or `failed` without a retry that can dispatch again.

### [MUST] FR-005: Prompt-injection and authority boundary

Email bodies, headers, attachments, and MCP tool results are untrusted data.
They may inform a triage classification but must never influence workflow
instructions, capability selection, approval, recipients, OAuth material, or
tool schemas.

Acceptance criteria:

- Given an email that asks the model to reveal secrets, ignore prior rules, or
  take a mailbox action, when the workflow runs, then it neither expands the
  tool surface nor performs a side effect.
- Given hostile or irrelevant tool prose, when the model receives it, then it
  cannot change the fixed package budget, model binding, or output contract.
- Given any run, when traces, receipts, or checked-in acceptance evidence are
  inspected, then they contain no OAuth token, authorization code, callback
  value, raw tool schema, or mailbox content.

### [MUST] FR-006: No mailbox mutation

The workflow must not send, reply, create Fastmail drafts, mark messages,
move, archive, delete, label, unsubscribe, create notes, modify contacts, or
change calendar data.

Acceptance criteria:

- Given any user prompt or email content, when the workflow runs, then it
  dispatches only the declared read-only capability or no remote capability.
- Given a later requirement for any mutation, when it is proposed, then it is
  specified and authorized as a separate feature with a current reviewed tool
  contract, explicit side-effect classification, argument provenance, action
  ledger, and dispatch approval policy.

## Terminal output contract

The host returns a bounded report with this logical shape. Its exact transport
encoding must follow the existing DAR package contract.

```json
{
  "status": "complete | needs_review | failed",
  "window": "previous_24_hours",
  "matched_count": 0,
  "truncated": false,
  "items": [
    {
      "message_reference": "opaque user-visible reference",
      "subject": "message subject when returned by the reviewed tool",
      "classification": "urgent | needs_reply | fyi | needs_review",
      "rationale": "concise explanation",
      "proposed_reply": "optional unapproved text"
    }
  ],
  "warnings": []
}
```

`matched_count` and `items` are each limited to five. The host must omit fields
the reviewed tool does not return rather than fabricating them.

## Non-functional requirements

- [MUST] NFR-001 Privacy: credentials, OAuth flows, raw MCP schemas, raw
  mailbox content, and raw tool results remain outside package artifacts and
  checked-in evidence.
- [MUST] NFR-002 Reliability: all capability, authentication, model-binding, and
  schema failures fail closed before dispatch; an indeterminate query is never
  presented as a complete triage.
- [MUST] NFR-003 Auditability: retain only redacted status, digest,
  dispatch-count, and bounded diagnostic evidence consistent with existing DAR
  trace policy.
- [MUST] NFR-004 Testability: tests use fakes and prove the tool, model binding,
  output, redaction, injection, and zero-mutation boundaries. A live Fastmail
  test is optional human acceptance, never a unit test.

## Edge and error cases

- E-001: no matching unread messages produces an empty, non-truncated `complete`
  report.
- E-002: more than five matches produces a `complete` report marked
  `truncated: true`.
- E-003: no model binding, connection, approved tool, or matching current schema
  produces a redacted pre-dispatch failure.
- E-004: an MCP timeout, malformed response, or ambiguous read outcome produces
  `failed` or `needs_review`, never a second automatic tool call.
- E-005: hostile email content may be classified but cannot alter authority or
  result in a side effect.

## Domain vocabulary

- *reviewed surface*: host-approved MCP tool identity and input-schema snapshot
  for the configured Fastmail connection.
- *message reference*: an opaque user-visible output value with no action
  authority.
- *triage*: classification and optional proposal only; it excludes all mailbox
  changes.

## Boundaries

- In scope: one saved llama.cpp Qwen-local-model workflow, strict
  current-surface binding, a single bounded `search_email` dispatch, and a
  terminal triage report.
- Out of scope: the features listed below.
- Always do: fail closed on host/model-binding/surface failures and treat email/tool
  content as untrusted data.
- Ask first: every live Fastmail invocation, mutation, model-binding change, or
  new MCP capability.
- Never do: configure Fastmail/OAuth from the model, expand the surface, or
  mutate Fastmail state.

## Out of scope

- All Fastmail mutations, including send, reply, draft creation, mark, move,
  label, archive, delete, unsubscribe, note, contact, and calendar operations.
- Automatic scheduling, notifications, durable inbox state, or cross-run
  memory.
- General-purpose Fastmail exploration, connection setup, OAuth consent,
  credential management, or MCP-surface review from a package or model.
- Additional MCP capabilities, attachments, raw message storage, retrieval
  infrastructure, and embeddings.

## Dependencies and assumptions

- Dependency: the implemented DAR workflow-host runtime, OAuth-discovery and
  reviewed-surface path, direct llama.cpp adapter, and the recorded local GGUF
  availability described in the prerequisite artifacts.
- Assumption: a human host administrator has configured and reviewed the
  connection and model binding before a run; the package cannot do so.
- Assumption: `search_email` can express the read-only time, unread, and result
  constraints through its current reviewed schema. If preflight disproves that,
  this specification requires revision before implementation.

## Open questions

P0 must name and qualify the exact llama.cpp configuration fingerprint. The
current reviewed Fastmail preflight must separately prove that its schema can
express the host-owned bounded query; P0 does not prove Fastmail compatibility.
