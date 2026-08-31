# MCP OAuth Discovery and Dynamic Registration Validation

## Automated Matrix

| Case | Required result |
| --- | --- |
| Correct Bearer challenge and protected-resource metadata | Canonical endpoint binds exactly; only digest/opaque record persists. |
| Challenged scope, advertised scopes, or neither | Challenged scope is authoritative; otherwise human confirms advertised scopes or an omitted `scope` value through a non-machine-readable view. |
| Missing, invalid, oversized, redirected, or resource-mismatched protected-resource metadata | Fails closed with a redacted discovery status. |
| RFC 8414/OIDC issuer mismatch, discovery redirect, or malformed/non-HTTPS authorization endpoint | Fails closed before registration or authorization. |
| Zero or multiple compatible authorization servers | No automatic selection or registration. |
| Valid public-client registration | Explicit `none`/S256 and code/refresh support, a stable generic client name, non-empty client ID, and an exact `localhost` port-variable registration template paired with a `127.0.0.1` ephemeral callback yield one bounded reused registration. A missing response-type advertisement is a bounded compatibility case; explicit empty or incompatible response types fail closed. |
| Missing registration metadata or declared unsupported DCR capability | Leaves the connection in explicit human-client setup; it neither manufactures credentials nor starts DCR. |
| Registration response requires a secret/management credential or has unsupported authentication/redirect | Fails closed; no credential or registration is stored. |
| Authorization callback has wrong loopback host, port, path, state, or required issuer | Code is not exchanged and credentials remain unchanged. |
| Authorization, code, or refresh request has an absent/different resource indicator | Request fails before a token can bind to the wrong audience. |
| Refresh succeeds with rotation | Credential replacement is atomic and bound to the same connection. |
| Pre-authorization metadata revalidation finds drift | Returns `metadata_drift`; browser launch, credential replacement, and tool dispatch do not occur. |
| Refresh fails or metadata drifts during reconnect | Returns `authentication_required` or `metadata_drift`; browser is not launched and no tool call is retried. |
| Successful OAuth setup without reviewed surface | No remote handler or executable workflow binding exists. |
| Secret-exclusion inspection | Packages, model inputs, traces, audit records, and receipts contain no raw OAuth/registration material. |
| Each FR-8 failure family | Emits only its stable redacted status and opaque identifiers; raw endpoint, metadata, registration, and OAuth values are absent. |

## Human Acceptance Run

After `threat-model.md` is approved, the automated matrix is green, and the G2
`MCPConnectionClient` has a protocol-conforming authenticated `tools/list`,
reviewed-surface snapshot, and binding path, an explicitly consenting user may
run the following generic workflow acceptance sequence against Fastmail:

1. Configure the `https://api.fastmail.com/mcp` endpoint through the human-only
   control plane, allowing discovery and dynamic registration.
2. Complete consent through the loopback callback and review the current
   read-only MCP surface.
3. Bind a saved workflow whose declared task is “show me the subject of the
   last five emails I received.”
4. Review the package specification and a redacted terminal transcript. Retain
   only package/transcript digests, terminal status, and dispatch counts.

The run fails if the process asks the workflow model or plugin skill for an
endpoint, a callback value, a client identifier, a token, or an unreviewed tool
surface. It also fails if it sends mail, retains mailbox content, or treats an
OAuth connection as a reviewed executable binding.
