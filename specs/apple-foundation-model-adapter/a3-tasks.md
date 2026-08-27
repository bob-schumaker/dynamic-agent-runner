<!-- markdownlint-disable MD013 -->
# Apple Foundation Models A3 Sealed-Host Task List

Status: planned

This is the canonical A3 task list. It implements `a3-plan.md` and FR-17 in
`spec.md`. All implementation tasks are test-first: add focused tests, observe
their failure, implement the smallest change, then rerun them green.

## C0 — Characterize current host limits

- [ ] C0.1 [tests] Add focused host/profile tests proving the current HTTP
      profile requires a loopback base URL and `LocalWorkflowHost.open` builds
      only the HTTP local adapter.
- [ ] C0.2 [tests] Add a saved-workflow characterization proving an async Apple
      adapter cannot currently cross the sealed runner boundary; preserve the
      current HTTP profile registration and invocation behavior as regression
      coverage. Also characterize the current same-alias cross-profile path and
      default adapter-coverage fallback as failures that A3 must close.
- [ ] C0.3 [analysis] Record the minimal adapter protocol change required for
      the runner, including which synchronous and async execution paths own
      model-call normalization and provider interruption propagation. Record
      the active-event-loop behavior: it must fail closed with a package-owned
      error unless A3 adds and tests a bounded async host entry point; nested
      loop workarounds are forbidden.

## C1 — Human-configured Apple profile

- [ ] C1.1 [tests] Add RED profile/control-plane tests for an Apple profile:
      model alias only, no HTTP base URL, no credentials, no asset path, and
      no workflow-provided provider selection.
- [ ] C1.2 [implementation] Add the bounded Apple profile record and
      human-only CLI configuration command. Preserve existing HTTP-profile
      schemas, receipts, and state records.
- [ ] C1.3 [tests] Add RED/GREEN eligibility tests for unsupported platform,
      absent optional SDK, unavailable Apple system model, and failed Apple
      preflight. Each fails before MCP client initialization or handler
      dispatch, with redacted package-owned errors.

## C2 — Sealed runner adapter selection

- [ ] C2.1 [tests] Add RED host-open and registration tests proving an Apple
      profile constructs the canonical Apple async adapter, advertises only its
      configured alias, and retains strict-local profile validation. Prove a
      registration is bound to the exact configured profile ID, including an
      HTTP-to-Apple same-alias mismatch.
- [ ] C2.2 [implementation] Adapt the sealed runner's narrow adapter boundary
      to execute the existing synchronous HTTP adapter and canonical async Apple
      adapter without a generic provider registry or changed HTTP behavior.
      Select strict adapter coverage for both paths and reject profile/coverage
      mismatches before sealed-input consumption, provider work, MCP
      initialization, or handler dispatch.
- [ ] C2.3 [tests] Retain one HTTP sealed-run regression. For Apple, prove
      sealed prompt consumption, terminal-output shaping, redacted traces, and
      async cancellation/error propagation. Prove an active-loop synchronous
      host call fails closed with the package-owned error unless the approved
      bounded async host entry point exists. Prove a package-requested alias
      outside strict coverage cannot fall back to a default adapter.

## C3 — Apple callbacks through host-owned MCP binding

- [ ] C3.1 [tests] Add RED fake Apple-host workflow coverage with one reviewed
      read-only MCP tool. Prove only the bound current surface reaches the Apple
      session and no raw handler/registry is exposed. The reviewed read-only
      call requires no provider approval and dispatches once.
- [ ] C3.2 [implementation] Wire the existing A2 active adapter tool context
      through the sealed host runner without bypassing coordinator ownership.
- [ ] C3.3 [tests] Prove the sealed-host composition preserves the A2 entry
      point: the reviewed read-only call runs once; an approval-required fake
      tool remains unresolved and never reaches a handler; and host
      traces/state/results remain DAR-owned. Keep the A2 suite as regression
      coverage for schema translation, callback budgets, lifecycle details, and
      the complete approval-decision matrix. Do not add a host decision
      collaborator unless separately approved.

## C4 — Validation and Fastmail O7 continuation

- [ ] C4.1 Run focused host/profile/runner/Apple tests, then full pytest, Ruff,
      package checks, and focused pre-commit.
- [ ] C4.2 On an eligible Mac, run a direct Apple-backed saved no-tool workflow
      and a fake-MCP Apple-backed saved workflow. Record only redacted live
      receipts; pytest-native Apple behavior remains diagnostic.
- [ ] C4.3 [tests] Before OAuth/live invocation, preflight the current reviewed
      Fastmail `search_email` descriptor through the Apple schema translator.
      Retain only a redacted surface digest and admissible/blocked result. An
      inadmissible schema blocks O7; do not weaken it.
- [ ] C4.4 Re-run the approved Fastmail O7 acceptance with the Apple profile
      only after C4.3 is admissible: confirm OAuth reconnect, certificate pin,
      current `tools/list`, and a `search_email`-only reviewed snapshot; invoke
      the saved last-five-subjects workflow once and retain only
      package/transcript digests, terminal status, and dispatch count for human
      review.
- [ ] C4.5 Update the Apple and OAuth validation records, task statuses, and
      portfolio summaries only after human review accepts the redacted Fastmail
      evidence. Do not check in mailbox content, OAuth material, or raw tool
      results.
