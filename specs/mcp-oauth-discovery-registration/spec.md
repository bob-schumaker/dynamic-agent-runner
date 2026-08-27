# MCP OAuth Discovery and Dynamic Registration Specification

## Metadata

- Feature slug: `mcp-oauth-discovery-registration`
- Mode: `light`
- Artifact type: authoritative SDD feature specification
- Status: implemented through O6; O7's opt-in Fastmail acceptance awaits human
  review of the specification and redacted terminal transcript
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related specifications:
  - `specs/mcp-runtime-integration/spec.md`
  - `specs/dar-authoring-plugin/spec.md`
  - `specs/approval-interruption-resume/spec.md`

## Objective

Let a human configure an HTTPS MCP connection whose server advertises OAuth
metadata, then let the DAR host discover that metadata and dynamically register
a loopback-PKCE public client where the server supports it. The resulting
connection is host-owned and may later supply an already-reviewed MCP tool
surface to a saved workflow. A package, plugin skill, workflow model, or tool
call cannot start discovery, registration, consent, or credential handling.

## Motivation and Boundary

The configured HTTPS MCP path implemented by the DAR authoring work already
has explicit OAuth Authorization Code with PKCE setup. It requires a
human-supplied authorization endpoint, token endpoint, and client identifier.
That is insufficient for an MCP server such as Fastmail that advertises OAuth
protected-resource metadata and dynamic client registration.

This feature is generic OAuth/MCP host support, not Fastmail functionality. It
does not change `dar-authoring` into an MCP server or grant its skills a
provisioning command. The authoritative currently-live configured HTTPS adapter
is the G2 `MCPConnectionClient` and reviewed-surface contract in
`dar-authoring-plugin`; the older `mcp-runtime-integration` v1 baseline has no
live transport or discovery capability. This specification owns only the OAuth
credential-bootstrap path for an explicitly human-configured HTTPS MCP endpoint.
O6 and live acceptance depend on that G2 adapter having a protocol-conforming
`tools/list` surface snapshot and binding path.

## References

- [Fastmail: Connecting AI tools via Fastmail's MCP server](https://www.fastmail.help/hc/en-us/articles/15869557281295-Connecting-AI-tools-via-Fastmail-s-MCP-server)
- [Fastmail: An MCP server for Fastmail](https://www.fastmail.com/blog/an-mcp-server-for-fastmail/)
- [RFC 9728: OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728)
- [RFC 8414: OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 7591: OAuth 2.0 Dynamic Client Registration](https://www.rfc-editor.org/rfc/rfc7591)

The Fastmail endpoint is an acceptance reference only. On 2026-08-26 its MCP
challenge advertised protected-resource metadata and its authorization-server
metadata advertised a registration endpoint and `none` token-endpoint client
authentication. Its registration endpoint also requires a public `client_name`
and its metadata omits `response_types_supported`; these compatibility facts
must be revalidated during implementation and must not create a provider branch.
Neither URLs nor scopes are package constants.

## Non-Goals

- Discovering an MCP endpoint, selecting a server, or accepting an endpoint
  from package/model input.
- Supporting arbitrary OAuth grants, confidential clients, device flow, or
  client-secret storage.
- Automatically choosing between multiple authorization servers or scopes.
- Automatically approving tools, widening a reviewed surface, or invoking a
  remote MCP tool.
- Retaining bearer tokens, authorization codes, callback query values, client
  registration responses, or raw OAuth metadata in package artifacts, model
  context, workflow traces, or receipts.
- Replacing an explicit manually registered public-client configuration when a
  server does not advertise dynamic registration.

## Trust and Ownership Model

| Actor | May do | Must not do |
| --- | --- | --- |
| Human host administrator | Choose the endpoint and offered scopes, start consent, review surface drift, disconnect the connection. | Delegate those decisions to a package or model. |
| DAR host control plane | Fetch/validate metadata, register/reuse a public client, run loopback PKCE, store opaque references, refresh credentials. | Expose secret or callback material to skills, packages, traces, or models. |
| Workflow package | Declare a stable connection requirement and reviewed semantic tool identifiers. | Contain endpoints, scopes, OAuth metadata, client IDs, credentials, or registration output. |
| Plugin skill or workflow model | Ask the human for required setup and invoke a saved workflow. | Invoke a discovery, registration, authorization, or surface-review command. |

## Functional Requirements

### FR-1: Human-only connection initiation

The control plane shall accept an HTTPS MCP endpoint only from an authenticated
human setup operation. It shall bind all resulting records to a canonical
endpoint and opaque connection ID. Package finalization, registration, and
`dar-package invoke` shall accept neither endpoint nor OAuth fields.

### FR-2: Bounded protected-resource discovery

For an unauthenticated configured endpoint, the host shall obtain protected
resource metadata from the Bearer `resource_metadata` challenge or the RFC 9728
well-known locations. It shall prefer a parsed challenge value; when absent, it
shall try the endpoint-path well-known URI, then the root well-known URI. It
shall use HTTPS, prohibit automatic redirects, bound response bytes, parse only
valid JSON objects, and require the metadata `resource` to exactly equal the
canonical configured endpoint.

The host shall parse a bounded Bearer-challenge `scope` value with the metadata.
That challenged scope set is authoritative for the attempted MCP request; it is
not assumed to be a subset, superset, or match for `scopes_supported`. When no
challenge scope exists, `scopes_supported` is optional and a missing value means
the authorization request omits `scope` rather than inventing one.

The host shall retain a digest and selected safe fields, not the raw response.
Absent, malformed, oversized, redirected, or mismatched metadata shall fail
closed with a stable redacted discovery status.

### FR-3: Authorization-server selection and scope binding

The host shall require exactly one compatible HTTPS authorization server for
automatic setup. Multiple candidates require a new human selection interface;
this first slice must not guess. For the selected issuer it shall try the MCP
required ordered discovery locations: RFC 8414 OAuth metadata with path
insertion, OIDC discovery with path insertion, then OIDC discovery with path
appending. It shall prohibit redirects, bound response bytes, require the
returned `issuer` to exactly equal the selected issuer, and accept only absolute
HTTPS authorization and token endpoint URIs with no fragment or userinfo. When
present, the registration endpoint must meet the same rule. Missing registration
metadata leaves the connection in the existing explicit human-client setup path;
malformed, substituted, or incomplete authorization metadata fails closed.

A human-only setup view shall show the validated endpoint identity, challenged
scope when present, and advertised scopes when present. It shall require the
human to confirm the exact challenged set; otherwise the human may choose a
least-privilege set from `scopes_supported`, or confirm an omitted `scope` when
that field is absent. `offline_access` may be selected only for requested
persistent reconnect when there is no challenged scope, or when the challenged
set already includes it. The host persists an immutable effective-scope
digest/reference bound to the connection; the display is never returned in a
machine-readable receipt, trace, package, or model-facing surface. A package
cannot add or replace scopes.

In v1, the human-only `create-mcp-connection` operation is the confirmation
operation: it records the selected set before authorization, and authorization
revalidates that set against current discovered metadata. An empty OAuth
connection may be used solely to obtain the human setup view; after reviewing it,
the administrator creates a separate connection with the selected scope set.
Changing the selection requires a new connection. This intentionally avoids a
model-callable or mutable scope-update command.

### FR-4: Dynamic public-client registration

When valid server metadata exposes a registration endpoint,
`token_endpoint_auth_methods_supported` explicitly contains `none`, and
`code_challenge_methods_supported` explicitly contains `S256`, the host shall
dynamically register one loopback-PKCE public client for the host installation,
authorization-server issuer, redirect template, and effective scopes. The
server metadata must explicitly support the `code` response type and the
Authorization Code and refresh-token grants. For compatibility, a missing (not
an empty or incompatible) `response_types_supported` member may proceed only
when every other listed public-client prerequisite is explicit and the bounded
DCR response exactly confirms the requested non-secret client. The registration
request shall declare the stable generic `client_name: Dynamic Agent Runner`,
Authorization Code and refresh-token use, `token_endpoint_auth_method: none`,
and exactly one v1 redirect template:
`http://localhost/<issuer-bound-path>` with no port. The generated path is
unique to that authorization-server issuer. The host binds only `127.0.0.1`,
then sends a `127.0.0.1:<ephemeral-port>` redirect URI with that path. This
relies on the native-app loopback exception that permits an ephemeral port and
the numeric loopback alias for a registered `localhost` prefix; a provider
that rejects it requires a separate human-approved redirect handler.

The host shall reuse a valid registration rather than registering on every
authorization attempt. It shall persist only the opaque host-owned registration
record and necessary non-secret client identity fields. Registration and
registration-response exchanges shall use HTTPS without automatic redirects and
bounded request/response bodies. A successful response must contain a non-empty
`client_id`, exact `token_endpoint_auth_method: none`, and the exact registered
redirect template. Any `client_secret`, `registration_access_token`, unsupported
authentication, malformed redirect, or malformed response fails closed and is
not persisted. A server that does not offer usable registration remains an
explicit human-configuration case; the host must not manufacture credentials.

### FR-5: Listener-first authorization-code PKCE

Before opening an authorization URL, the host shall bind an ephemeral loopback
listener on `127.0.0.1` and generate one-use state and S256 PKCE
verifier/challenge. It shall select an ephemeral port and form the authorization
redirect URI by adding that port to the registered v1 template. The authorization
request and both authorization-code and refresh token requests shall send the
same canonical protected-resource `resource` value. The authorization request
shall otherwise use the discovered endpoint, selected public client ID, exact
redirect URI, and effective scopes. The callback shall accept one request,
validate the exact `127.0.0.1` URI including port/path, state, and issuer when
the authorization-server metadata requires an issuer parameter, then exchange
its code once. `localhost`, IPv6 loopback, a different port, and a different
path are not v1 aliases.

Code and refresh exchanges shall use the exact discovered HTTPS token endpoint,
prohibit redirects, and bound the response before JSON parsing.

The listener, authorization URL, code, state, verifier, callback query, token
response, and registration response are secret-adjacent operational material.
They shall not appear in packages, skill output, model input, ordinary traces,
or JSON receipts.

After accepting the one valid callback, the loopback listener shall return a
static, non-cacheable HTML acknowledgement stating that the OAuth token has
been received, the window may be closed, and the user should return to the
terminal. It shall include no callback query value, token, client, endpoint,
or other dynamic authorization material.

### FR-6: Credential lifecycle and drift

Access and refresh credentials shall remain in the operating-system credential
store under a connection-bound opaque reference. Refresh rotation shall replace
the secret atomically. On a failed refresh, the host returns
`authentication_required`; it does not launch a browser, re-register a client,
or retry a remote tool call that might have dispatched.

The host shall revalidate discovery metadata before an authorization flow and
after relevant authentication failures. A change to the protected resource,
issuer, effective scopes, client-registration binding, or authentication
endpoints invalidates the connection for human review; it must not silently
rebind credentials or a reviewed MCP surface.

### FR-7: Surface review remains separate

Successful authentication provides no executable MCP capability. The G2
`MCPConnectionClient` reviewed-surface path must retrieve and review a tool
identity/input-schema snapshot before any binding or dispatch. A registration
record, credential, or discovery result is not approval authority.

### FR-8: Redacted statuses and audit evidence

Control-plane output shall contain only opaque connection/operation identifiers,
stable status codes, timestamps, and digests where useful. It shall distinguish
at least `metadata_unavailable`, `metadata_invalid`,
`authorization_server_selection_required`, `registration_unavailable`,
`authorization_required`, and `metadata_drift`. Trace evidence may record
endpoint/metadata digests, byte counts, status, and dispatch counts, but never
raw metadata or sensitive OAuth values.

The separate human-only setup display is not a machine-readable receipt: it may
show the already configured endpoint and scope names to a process acting as the
same local OS principal that owns the host state. That principal is the v1 human
control-plane authority. Skills, packages, model requests, trace/audit records,
and ordinary command receipts receive no such display; a caller that can read
the private state root is already inside the local-principal authority boundary.

### FR-9: Testability

All automated tests shall use injected HTTP, clock, browser, listener,
credential-store, and MCP transport fakes. They shall cover strict discovery
binding and scope challenge precedence; RFC 8414/OIDC discovery and exact issuer
binding; oversized/invalid/redirected metadata; ambiguous issuer selection;
public-client capability/registration/reuse; loopback host/port/path checks;
PKCE/resource/state/issuer validation on authorization, code, and refresh
requests; refresh rotation; metadata drift; and proof that no secret-adjacent
values enter package, model, trace, or receipt surfaces. No live Fastmail or
other OAuth provider call belongs in unit tests.

## Acceptance Evidence

Implementation is ready for a separately approved human acceptance run when
the fake matrix in [`validation.md`](validation.md) passes and the G2
`MCPConnectionClient` exposes a protocol-conforming authenticated `tools/list`,
reviewed-surface snapshot, and binding path. That run may use Fastmail with the
user's consent to authenticate, inspect the server's current tool surface, and
execute a saved read-only workflow that requests the subjects of the last five
received emails. It must not retain email content, OAuth material, or tool
results in the checked-in evidence. Human review of the workflow specification
and redacted terminal transcript is the final gate.

## Delivery Plan

The commit-sized implementation slices are in [`plan.md`](plan.md); the
test-first work checklist is in [`tasks.md`](tasks.md).
