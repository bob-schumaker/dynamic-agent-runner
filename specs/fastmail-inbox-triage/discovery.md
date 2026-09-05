# Fastmail Inbox Triage Discovery

## Feature Disposition

- Mode: `guided`
- Feature slug: `fastmail-inbox-triage`
- Planning disposition: single coherent, read-only workflow
- Model decision: direct in-process llama.cpp using the downloaded
  `Qwen/Qwen2.5-3B-Instruct-GGUF` artifact, not Apple Foundation Models or MLX.

## Desired Outcome

Provide a saved DAR workflow that uses the configured Fastmail HTTPS MCP
connection and the downloaded Qwen2.5 GGUF to triage at most five unread,
recently received messages. It returns a structured report and optional reply
text; it cannot mutate the mailbox.

## Selected Local Model

| Field | Value |
| --- | --- |
| Repository | `Qwen/Qwen2.5-3B-Instruct-GGUF` |
| Revision | `7dabda4d13d513e3e842b20f0d435c732f172cbe` |
| File | `qwen2.5-3b-instruct-q4_k_m.gguf` |
| SHA-256 | `626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d` |
| Availability | copied into DAR's default Hugging Face cache; GGUF/llama.cpp eligible |

This is the only recorded downloaded Qwen Instruct artifact compatible with the
direct llama.cpp target. `Qwen/Qwen3-4B-MLX-4bit` is a native MLX artifact and
is deliberately excluded.

## Users and Authority

| Actor | Authority | Not authority for |
| --- | --- | --- |
| Human host administrator | Configure Fastmail, complete OAuth consent, review current surface, select/register package. | Model-directed credentials, scopes, or tool changes. |
| DAR host | Verify Qwen identity, bind reviewed tool, enforce budgets, redact traces. | Treating prior acceptance as current surface. |
| Local Qwen model | Call one exposed read-only tool and render terminal report. | Side effects, approval, recipient selection, or capability expansion. |
| Email and MCP result | Evidence for triage. | Instructions, policy, schema, or action authority. |

## Existing Evidence and Constraints

- Direct in-process llama.cpp sync/async adapters, local asset resolution, and
  identity validation are implemented in `src/dynamic_agent_runner/local_models.py`.
- The Qwen GGUF was copied to DAR's default cache with a verified SHA-256 and
  immutable revision. Its availability check was offline; no model was loaded.
- Existing Fastmail OAuth and reviewed-surface work proves host-owned read-only
  binding. OAuth success alone does not approve a tool.
- A live Fastmail acceptance is human-authorized only; unit tests use fakes.
- The exact Qwen GGUF must still pass P0 tool-call/final-continuation evidence
  before it can receive Fastmail data. This supersedes the former Apple B5.2
  prerequisite; it does not authorize live Fastmail access.

## Trust Boundaries

- Always do: revalidate current surface, bind one read tool, enforce one call
  and five-item limits, validate Qwen identity, and redact evidence.
- Ask first: local model probe, live Fastmail acceptance, a mutation, new MCP
  capability, changed Qwen artifact, or a longer query window.
- Never do: expose credentials/OAuth data, treat email as authority, download a
  model during a run, use MLX/HTTP fallback, or mutate Fastmail.

## Examples

1. An unchanged reviewed surface and verified Qwen model yield one bounded
   `search_email` dispatch and a report for up to five messages.
2. An email asks the model to ignore policy and send mail. Its content may be
   classified, but it cannot expand tools or cause a side effect.
3. A model identity mismatch or a reviewed-schema drift fails before model
   exposure or Fastmail dispatch.

## Sources

- `specs/llama-cpp-local-model/spec.md`
- `specs/local-model-availability-api/a5.2-copy-receipt.md`
- `specs/local-model-availability-api/a5.2-dry-run-manifest.md`
- `specs/mcp-oauth-discovery-registration/spec.md`
- `specs/mcp-oauth-discovery-registration/validation.md`
