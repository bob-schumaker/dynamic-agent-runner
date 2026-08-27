<!-- markdownlint-disable MD013 -->
# Apple Foundation Models A3 Sealed-Host Integration Plan

Status: planned

## Objective

Allow the sealed DAR-authoring host to run a registered workflow with the
existing Apple Foundation Models adapter. This is the missing boundary needed
for the consented Fastmail read-only acceptance: the current host always builds
an HTTP/LiteLLM local adapter from a base URL, while the Apple adapter is
on-device and async-only.

## Fixed decisions

- A3 extends `apple-foundation-model-adapter`; it does not create an
  Apple-specific Fastmail or OAuth feature.
- Apple is a strict-local, human-configured host profile with no base URL, API
  key, model path, downloaded-model reference, or workflow-controlled provider
  selection.
- The host must use the canonical Apple async adapter and preserve its A2
  provider callback path through DAR's coordinator. It must not wrap Apple in
  LiteLLM or create an Apple HTTP service.
- The current HTTP local-model profile retains its existing externally
  observable behavior. Registrations bind their original profile ID; a
  same-alias profile of another kind cannot run them.
- Eligibility failures occur before MCP initialization, surface discovery, or
  tool dispatch. No fallback to an HTTP adapter is allowed.
- A3 is complete only after fake coverage, an eligible-Mac saved-workflow live
  gate, and the consented Fastmail read-only O7 retry produce redacted evidence.

## Milestones

### C0 — Characterize the sealed host boundary

Write focused RED tests around `LocalWorkflowHost.open`, profile storage,
registration, and `WorkflowRunner` proving that the existing host profile
factory accepts only an HTTP profile and its runner annotation admits only the
sync adapter. Also prove an injected async adapter already runs through the
existing synchronous wrapper. Record the minimal type/factory changes without
changing execution behavior.

### C1 — Add an Apple host profile

Add a separate, human-only Apple profile configuration/control-plane command.
It records only the Apple model alias and strict-local capability metadata.
Reject base URL, credentials, arbitrary provider names, model assets, and
non-eligible hosts. Keep current HTTP-profile records and commands unchanged.

### C2 — Bind sealed execution to the selected profile

Extend the profile factory and runner annotation only enough to construct the
canonical async Apple adapter alongside the existing synchronous HTTP adapter.
Set strict adapter coverage and exact active-profile binding before sealed-input
consumption, provider work, MCP initialization, or handler dispatch. Preserve
the existing synchronous wrapper, failure classification, tracing, MCP binding,
approvals, and terminal-output shaping. Do not introduce a general provider
registry or a second host execution API.

### C3 — Preserve A2 tool behavior from the host

Add fake Apple-backed host workflow tests that expose one reviewed read-only MCP
tool. Prove wrapper creation uses the bound current surface; reviewed read-only
dispatch is once-only; an approval-required fake tool remains unresolved and never
reaches its handler; and traces/state/results remain DAR-owned. A2 remains the
regression authority for schema translation, callback budgets, and the complete
approval-decision matrix; A3 proves only that the sealed-host composition
enters that behavior.

### C4 — Eligible-Mac and Fastmail acceptance

On an eligible Mac outside the execution sandbox when required by Apple,
exercise an Apple-backed saved no-tool workflow and an Apple-backed saved MCP
workflow. Then retry O7 with Fastmail: use the already human-configured OAuth
connection, first establish from the redacted current-surface digest that the
reviewed `search_email` schema is admissible for an Apple wrapper, invoke the
saved task-specific package only if it is admissible, and retain only redacted
receipt/digest/dispatch evidence for human review.

## Non-goals

No generic multi-provider profile registry, HTTP façade, workflow-selected model
provider, Fastmail-specific runtime branch, browser automation change, durable
approval resume, or retention of mailbox/OAuth content is authorized.
