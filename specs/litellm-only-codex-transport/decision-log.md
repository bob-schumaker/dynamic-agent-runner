# LiteLLM-Only Codex Transport Decision Log

## Decisions

- 2026-09-05 — Postpone this feature until LiteLLM offers an upstream-supported
  ChatGPT Responses path that satisfies DAR's injected-auth, identity-header,
  and renderer requirements. Retain the direct SDK transport meanwhile and
  preserve this analysis as the future re-entry gate.
- 2026-09-05 — Keep `_ResolvedDefaultOpenAIProvider` inside
  `openai_client.py` as the credential-policy boundary. It already separates
  trusted discovery from transport construction; a second resolver abstraction
  would add no capability.
- 2026-09-05 — Use LiteLLM Responses for all ChatGPT/Codex model execution.
  DAR retains credential resolution, catalog lookup, request/response
  normalization, and error redaction.
- 2026-09-05 — Keep Codex catalog lookup as a DAR private injected HTTPS
  callable, not LiteLLM or an official-SDK client, so model execution has one
  transport without losing `client_version` or catalog semantics.
- 2026-09-05 — Reject conflicting injected `ChatGPT-Account-ID` values rather
  than silently selecting one.
- 2026-09-05 — Default cutover and direct-provider deletion require offline
  provider-transform evidence plus a manually authorized redacted live receipt.
- 2026-09-05 — Block implementation before factory rewiring: LiteLLM `1.98.0`
  invokes its own ChatGPT authenticator and emits session/originator behavior,
  which conflicts with DAR-only credential and identity policy. Proceed only
  with an approved exact upstream version/configuration that passes the offline
  feasibility probe, or amend the transport decision.
- 2026-09-05 — Treat `api_key`, base URL, provider marker, `Authorization`, and
  `ChatGPT-Account-ID` as DAR-owned identity inputs. Reject conflicting
  case-insensitive LiteLLM kwargs instead of permitting `setdefault` overrides.
- 2026-09-05 — Upstream-release research found no conforming upgrade path:
  LiteLLM current `main` retains the same ambient authenticator, session, and
  default-instruction behavior. The next step requires a scope decision, not a
  dependency update experiment.

## Rejected Options

- New generic resolver/OAuth module — conflates OpenAI/Codex policy with MCP
  OAuth lifecycle and duplicates the existing result seam.
- LiteLLM-managed Codex credential discovery — loses DAR's source precedence,
  trust boundary, and unsupported-mode policy.
- Retaining the direct SDK path indefinitely — leaves duplicate execution
  transports and renderer ownership.
- Production monkeypatching of LiteLLM private auth — would become an
  unsupported second transport implementation and drift with upstream.

## Drift Events

- 2026-09-05 — Corrected a malformed architecture text fence in `spec.md`
  before implementation handoff. Classification: progress-only documentation
  drift; no behavior or scope changed.

## Gate History

- Discovery gate: approved by existing reviewed spec and Council/Ponytail review.
- Spec gate: approved; status is ready for gated implementation.
- Plan gate: prepared by user request; implementation is not authorized to skip
  the feasibility or live cutover gates.
- Task gate: prepared; TDD is mandatory.
- Validation gate: pending implementation and manually authorized live receipt.
