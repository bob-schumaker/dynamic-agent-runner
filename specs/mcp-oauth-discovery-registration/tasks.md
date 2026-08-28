# MCP OAuth Discovery and Dynamic Registration Tasks

## Protocol and Records

- [x] RED/GREEN: add bounded fake fixtures for protected-resource metadata,
      authorization-server metadata, and dynamic registration. Prove fixtures
      have no secret, callback, or mailbox content.
- [x] Review and approve `threat-model.md` before O2. It must address malicious
      metadata/registration endpoints, callback interception and mix-up, redirect
      abuse, and credential or trace exfiltration.
- [x] RED/GREEN: implement strict protected-resource discovery from the Bearer
      challenge and RFC 9728 well-known location with exact configured-resource
      binding, challenge-scope parsing, HTTPS/size/no-redirect limits,
      digest-only persistence, and redacted failures.
- [x] RED/GREEN: implement authorization-server metadata validation and fail
      closed on zero or multiple compatible issuers. Cover ordered RFC 8414/OIDC
      discovery, exact issuer binding, and malformed/non-HTTPS/substituted
      endpoint values.
- [x] RED/GREEN: persist immutable human-selected scope and connection records;
      require challenged-scope precedence, provide a separate human-only scope
      confirmation view, and reject package- or model-provided endpoint and scope
      changes.

## Registration and Authorization

- [x] RED/GREEN: dynamically register and safely reuse a loopback PKCE public
      client only when metadata explicitly supports `none`, `S256`, and the
      required code/refresh capabilities; require the `localhost` port-variable
      redirect template and a `127.0.0.1` bound callback; retain explicit
      human-client setup when registration is absent or its declared
      capabilities are unsupported; and reject
      client-secret, registration-management credential, malformed response,
      host-alias, path, and port-mismatch paths.
- [x] RED/GREEN: extend listener-first PKCE with discovered endpoints, the
      protected-resource `resource` parameter in authorization, code, and refresh
      requests; exact callback/state validation; issuer validation where
      advertised; and one-time code exchange.
- [x] RED/GREEN: prove raw authorization and registration material is absent
      from packages, skills, model input, traces, audit records, and receipts.

## Lifecycle and Integration

- [x] RED/GREEN: atomically rotate refresh credentials, return
      `authentication_required` without browser launch on failure, and never
      retry a possibly dispatched remote call.
- [x] RED/GREEN: revalidate discovery immediately before every browser
      authorization flow and after relevant authorization/reconnect failures;
      invalidate the connection and reviewed surface on security-relevant drift
      before browser launch or remote-tool dispatch.
- [x] RED/GREEN: integrate only with the existing reviewed configured-HTTPS MCP
      G2 `MCPConnectionClient` surface path; prove authentication alone cannot
      construct a handler.
- [x] RED/GREEN: add human-only CLI/help/status and a capability report that
      expose opaque identifiers and stable redacted statuses only. Assert every
      FR-8 status on its corresponding failure path and prove raw endpoint,
      metadata, registration, and OAuth values never enter output or traces.

## Acceptance

- [x] Run the full focused fake suite, lint, and package build.
- [x] With explicit user consent, conduct the Fastmail read-only acceptance run
      and bind human review evidence to the package digest and redacted terminal
      transcript. Do not check in email content or OAuth material.
  - Completed with the Apple-backed `fastmail-last-five-subjects-apple-v2`
    package after the callback-result token budget fix.
- [ ] With fresh explicit user authorization, conduct the Fastmail mutation
      acceptance using the existing G5 authorized-binding path.
  - Before dispatch, reauthorize through Fastmail's human consent screen,
    inspect the newly advertised tools, and have the human choose one exact
    reviewed tool plus its `write` or `delete` classification.
  - Build a workflow that declares only that tool, explicitly selects its
    per-invocation approval policy, and supplies complete argument-provenance
    rules. Do not introduce `send` or an `all access` side-effect class.
  - RED/GREEN: first add fake coverage proving the generated descriptor rejects
    any missing approval, provenance, exact reviewed-tool mapping, or
    side-effect classification. Then prove the selected policy dispatches
    through either `workflow_auto` or `--ask`, records intent exactly once, and
    records a terminal ledger result.
  - [x] RED/GREEN: preserve authorized-MCP binding ownership of local approval
    through Apple Foundation callback wrappers. The generic provider coordinator
    must not emit `ProviderToolInterruption` before the binding can record its
    one intent, obtain the workflow-selected local decision, dispatch once, and
    record a terminal ledger result.
  - Run the focused G5 tests, lint, and a human-reviewed live action using the
    generated workflow's selected approval policy.
    Do not retain mailbox content, OAuth material, or raw tool results in the
    checked-in evidence.
