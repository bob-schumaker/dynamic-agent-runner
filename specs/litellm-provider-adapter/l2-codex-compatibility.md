# L2.1 Codex Compatibility Audit

## Status

- Slice: `L2.1`
- Status: complete
- Date: 2026-07-02
- Scope: compare the current DAR ChatGPT/Codex backend with the vendored
  LiteLLM ChatGPT provider before selecting an L2 transport.

## Current DAR behavior

The current `ChatGPTCodexBackend(Open|Async)OpenAIClientProvider`:

- receives the token and resolved endpoint from DAR-owned Codex auth discovery;
- passes the token as the OpenAI client API key and optional
  `ChatGPT-Account-ID` as a default header;
- sends the request through `client.responses.create(...)`;
- moves system/developer content into Responses `instructions`, preserving
  transcript items used by the tool loop;
- forces `store=False` and `stream=True` for the Codex backend;
- uses DAR-owned `client_version` query parameters for authenticated model
  listing, preserving catalog priority and visibility semantics;
- normalizes streamed Responses text and function calls into DAR
  `ModelResponse`, and wraps provider failures as `ModelExecutionError`.

## Vendored LiteLLM behavior

The local `litellm/llms/chatgpt` implementation provides both Chat Completions
and Responses transformations.

### Responses path

- Uses the ChatGPT `/responses` endpoint and forces streaming and `store=False`.
- Adds ChatGPT default instructions and encrypted reasoning-content inclusion.
- Preserves Responses tools, tool choice, reasoning, previous-response, and
  truncation fields through an explicit allowlist.
- Adds ChatGPT authorization, account id, session id, originator, user-agent,
  and event-stream headers.
- Its default authenticator reads LiteLLM-owned auth state unless the adapter
  supplies a resolved credential/configuration boundary.

### Chat Completions path

- Uses the ChatGPT chat-completions endpoint and Chat Completions messages.
- Adds the same ChatGPT authorization/account/session headers.
- Defaults streaming off and normalizes non-standard ChatGPT tool-call chunks.
- Requires conversion from DAR Responses input/tool shapes and cannot preserve
  all Responses-specific transcript and reasoning semantics.

## Compatibility matrix

| Concern | DAR current backend | LiteLLM Responses | Result |
| --- | --- | --- | --- |
| Auth ownership | DAR resolves Codex auth and token precedence | LiteLLM can discover its own auth | Keep auth discovery in DAR; inject resolved values |
| Endpoint | Resolved ChatGPT Codex backend URL | ChatGPT `/responses` URL | Compatible after explicit base URL mapping |
| Account header | DAR passes configured account id | LiteLLM derives account id and session headers | Inject DAR account id; test header spelling/case and precedence |
| Session id | DAR does not expose a LiteLLM session policy | LiteLLM generates/persists a session id | Decide whether generated session ids are acceptable; do not read new ambient auth |
| Instructions | DAR folds system/developer messages and defaults instructions | LiteLLM adds ChatGPT defaults and preserves explicit instructions | Compare ordering and deduplication; avoid double defaults |
| Streaming | DAR requires streamed Responses events | LiteLLM Responses reconstructs/normalizes SSE | Strong match; add event and tool-call tests |
| Tool calls | DAR preserves Responses tool-loop transcript items | LiteLLM Responses preserves Responses output items | Strong match; verify ids, arguments, and follow-up inputs |
| Model listing | DAR sends `client_version` and preserves priority/visibility | L1 LiteLLM provider has no equivalent listing contract | Keep DAR model listing outside the transport |
| Error handling | DAR exposes `ModelExecutionError` | LiteLLM raises provider-specific exceptions | Translate and redact at the DAR boundary |
| Chat Completions bridge | Not used for Codex | Requires shape and semantic conversion | Reject as the primary Codex path |

## L2.1 decision

The Codex replacement must use LiteLLM's Responses surface, with
`aresponses(...)` as the async-first path and `responses(...)` for sync parity.
The adapter must preserve DAR-owned auth discovery, model listing, auth
precedence, account-id forwarding, and normalized error behavior. LiteLLM's
ambient authenticator must not silently replace those policies.

Chat Completions bridging is acceptable only as an explicitly capability-gated
fallback for providers that lack Responses support; it is not a Codex-equivalent
implementation because it can lose Responses transcript items, reasoning
metadata, tool-call identity, and streaming semantics.

## L2.2 inputs and remaining validation

This audit supplies L2.2 with the following transport requirements:

1. Implement `aresponses(...)` first and `responses(...)` second.
2. Pass DAR-resolved token, base URL, and account id explicitly.
3. Compare LiteLLM and DAR instruction defaults and session-id behavior.
4. Add fake tests for streamed text, tool calls, follow-up transcript items,
   model-listing isolation, token-limit handling, and secret redaction before
   changing the default Codex provider.

## Drift review: current migration decision

The post-L2.2-L2.6 drift review ran the focused provider/auth tests and the full
DAR suite. Focused coverage passed `113 tests`; the full suite passed `676
tests, 4 skipped`; Ruff passed.

The review confirms that the opt-in wrapper preserves the tested request
contract, but it does not authorize replacing the global ChatGPT/Codex default:

1. **Auth ownership remains a blocker.** LiteLLM's ChatGPT Responses
   `validate_environment()` invokes its own `Authenticator.get_access_token()`
   and `get_account_id()`. The current upstream path can therefore read
   LiteLLM-owned auth files or initiate device authentication instead of using
   the DAR-resolved token. Explicit DAR token injection is tested at the
   wrapper seam but is not yet proven end-to-end through LiteLLM's ChatGPT
   transformation.
2. **Model listing remains a blocker.** DAR's authenticated model listing
   carries `client_version` and preserves provider priority/visibility. The
   wrapper supports an injected model-list callable, but LiteLLM does not yet
   provide an equivalent contract that can safely replace DAR's listing path.
3. **Runtime packaging no longer blocks native Responses.** The bundled fallback
   was retired after upstream LiteLLM became a Python 3.14-compatible runtime
   dependency. This removes a packaging blocker but does not resolve the auth
   and model-listing blockers above.

Current decision: ordinary OpenAI-compatible requests may use LiteLLM; Codex
through LiteLLM remains opt-in behind the explicit wrapper and model-list seam;
the SDK-backed ChatGPT/Codex provider remains the global default until these
three blockers have live parity evidence and an approved migration slice.
