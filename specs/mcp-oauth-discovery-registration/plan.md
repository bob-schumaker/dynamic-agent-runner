# MCP OAuth Discovery and Dynamic Registration Plan

## Status

Implemented through O6. O7's opt-in Fastmail read-only run is authorized but
blocked pending the Apple-backed sealed-host profile work in
`../apple-foundation-model-adapter/a3-tasks.md`; human review of the
specification and redacted terminal transcript remains required before claiming
this integration live. This extension does not reopen the completed generic MCP
baseline or change the plugin's skills-only control-plane direction.

## Commit-Sized Slices

1. **O1 — Freeze the protocol contract.** Add de-identified protected-resource,
   authorization-server, and registration fixtures plus the reviewed
   [`threat-model.md`](threat-model.md). It must cover malicious metadata and
   registration endpoints, callback interception/mix-up, redirect abuse, and
   credential/trace exfiltration before O2 begins. Record the Fastmail
   observation as non-authoritative reference evidence. Verify fixtures contain
   no credential, authorization code, callback, or email data.
2. **O2 — Protected-resource discovery.** Write failing fake-HTTP tests for
   Bearer challenge and RFC 9728 well-known discovery, exact resource binding,
   HTTPS/size/no-redirect rules, challenge-scope parsing, and redacted statuses.
   Implement only the parser and host-owned discovery record needed to pass them.
3. **O3 — Authorization-server metadata and scope selection.** Add failing
   tests for the ordered RFC 8414/OIDC discovery locations, exact issuer and
   endpoint validation, explicit ambiguous issuer failure, challenged-scope
   precedence, and immutable human-confirmed scope binding. Implement the
   records and human-only display contract without browser or registration calls.
4. **O4 — Dynamic public-client registration.** Add failing fake-HTTP and
   credential-store tests for explicit `none`/S256 and code/refresh support,
   the bounded missing-`response_types_supported` compatibility case (while
   rejecting an explicitly empty or incompatible member), the required generic
   client name,
   the exact `localhost` redirect template with a `127.0.0.1` ephemeral
   callback URI, bounded response validation,
   installation/issuer/scope reuse, explicit-client fallback when registration
   is absent or metadata-declared capabilities are unsupported, and fail-closed
   secret or malformed-response cases.
   Implement the registration service.
5. **O5 — Discovered PKCE authorization.** Extend the existing listener-first
   flow test-first with discovered endpoints, `resource` in authorization, code,
   and refresh requests, issuer callback validation where advertised, exact
   loopback host/port/path checks, and redaction proof. Keep explicit legacy
   public-client setup compatible.
6. **O6 — Refresh, drift, and surface handoff.** Test atomic refresh rotation,
   metadata revalidation immediately before every browser authorization flow and
   after relevant authentication/reconnect failures, invalidation on
   security-relevant drift, and the fact that a successful connection still has
   no executable handler until the G2 `MCPConnectionClient` reviewed-surface
   binding succeeds.
7. **O7 — Human acceptance and documentation.** Add control-plane help and
   redacted receipts, run the full fake suite and package verification, then
   conduct the opt-in Fastmail read-only acceptance run. Human review of the
   specification and redacted terminal transcript is required before claiming
   this integration live.

Each slice begins with focused tests that demonstrate the missing behavior,
records the RED result, implements the smallest boundary, and reruns GREEN
before its commit.

## Dependency and Rollout Rules

- O1–O6 are DAR runtime work. `dar-authoring` changes only after those slices
  expose a human-only setup path and capability report.
- Plugin skills never learn a client ID, authorization URL, callback address,
  endpoint, token, or raw tool surface. They may report that human setup is
  required for a declared stable connection requirement.
- A live-provider test is acceptance evidence, not a unit-test fixture and not
  a release substitute for the fake security matrix.
- Docker is not a requirement. If a portable isolated acceptance environment is
  later wanted, specify it separately rather than making it a prerequisite.
