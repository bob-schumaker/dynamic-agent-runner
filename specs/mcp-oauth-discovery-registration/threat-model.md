# MCP OAuth Discovery and Dynamic Registration Threat Model

## Status

Approved by the final security council review on 2026-08-26 after the focused
fake suite verified the listed controls. This records O1 protocol approval only;
it does not approve live-provider acceptance or tool-surface dispatch.

## Assets and Trust Boundaries

The host protects the selected MCP resource identity, authorization code, PKCE
verifier, state, access/refresh tokens, client registration record, reviewed MCP
surface, and mailbox/tool output. The human setup view is trusted to confirm the
endpoint and scopes. Packages, skills, workflow models, remote MCP prose, and
machine-readable receipts are untrusted for provisioning authority.

## Required Attacker Paths and Controls

| Attacker path | Required control | Proof |
| --- | --- | --- |
| Malicious challenge, protected-resource metadata, or authorization metadata substitutes resource, issuer, or endpoint. | HTTPS/no-redirect bounded discovery; exact resource and issuer binding; validated endpoint URIs. | Fake metadata mismatch, redirect, size, and endpoint-substitution tests. |
| Malicious registration response creates a confidential or manageable client. | Explicit `none`/S256 capability; reject client secret and registration-management credentials; exact redirect template. | Fake registration-response negatives and persistence inspection. |
| Local process intercepts or injects callback, or mixes authorization servers. | Listener-first `127.0.0.1`, one callback, PKCE, state, issuer-bound path, exact callback URI. | Host/port/path/state/issuer mismatch tests. |
| Redirect endpoint reaches a non-loopback listener or unexpected route. | Register only the `localhost` loopback template; bind and accept only `127.0.0.1` with a variable port and exact issuer-bound path; no IPv6 aliases. | Registration and callback mismatch tests. |
| Token is minted or refreshed for another resource. | Same canonical `resource` on authorization, code, and refresh requests. | Resource-indicator mismatch tests. |
| Package/model/trace exfiltrates OAuth or registration material. | Human-only setup; OS credential store; redacted status and digest-only evidence. | Package/model/trace/receipt exclusion tests. |
| Authentication is mistaken for tool authorization. | Separate current reviewed-surface snapshot and binding gate. | Authentication-only connection has no handler test. |

## Residual Risk and Decision

Loopback redirects cannot prove the identity of every local process. This slice
reduces interception and mix-up risk with PKCE, state, an issuer-bound path, and
an external browser, but does not claim platform attestation. A provider that
cannot honor the exact v1 loopback policy is unsupported by dynamic registration
and requires a separately approved human redirect handler.
