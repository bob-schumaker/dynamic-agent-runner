# OpenAI-Compatible External Adapter Implementation Plan

Status: Approved

## Spec Trace

- Spec: `specs/openai-compatible-external-adapter/spec.md`
- Protocol authority: `specs/external-model-adapter-protocol/spec.md`
- Repository guardrails: `AGENTS.md` and `AGENTS.local.md`
- Planning mode: guided; implementation must not begin until this plan and its
  later task breakdown are approved

## Objective

Deliver one direct, explicitly configured `DARExternalAdapterProtocol`
implementation for a single OpenAI-compatible endpoint and model. The adapter
must reuse DAR's request/response types and existing provider normalization,
remain independent of the receiver registry, and pass deterministic fake
transport tests without changing the OpenAI/LiteLLM default path.

## Current state

- `external_adapter.py` owns the exported protocol, descriptor validation,
  request context, façade, bounded dispatch, redaction, and single-use tokens.
- `openai_client.py` owns `OpenAIModelRequest`, `ModelResponse`, model-list
  normalization, request construction, response normalization, and explicit
  official-SDK provider factories.
- `local_models.py` exposes an OpenAI-compatible endpoint adapter, but it is a
  legacy `ModelAdapter` and has no external-protocol descriptor or health
  boundary.
- The receiver registry accepts zero-argument packaged factories and therefore
  cannot bind arbitrary endpoint credentials/configuration in this slice.

## Scope and ownership

### In scope

1. A new package-owned module, preferably
   `src/dynamic_agent_runner/openai_compatible_external.py`, containing the
   configured adapter, non-secret config, explicit transport protocols, URL
   policy, and model-inventory validation.
2. Sync and async transport construction over the existing explicit
   OpenAI-compatible client boundary, with default-auth discovery disabled.
3. Exact adapter/model identity, bounded health, structured-output validation,
   model-returned tool-call normalization, timeout/cancellation handling, and
   redacted package-owned failures.
4. Public exports for the config and factory helpers.
5. Fake transport tests, coordinator re-entry tests, regression tests, and a
   concise README usage example.

### Out of scope

- Changes to `DARExternalAdapterProtocol` or its wire ID.
- Receiver-registry configuration binding, packaged dynamic service plugins,
  or CLI lifecycle commands.
- Service process lifecycle, model downloads, endpoint discovery, streaming,
  embeddings, multimodal output, persistent sessions, or native callbacks.
- Changes to existing OpenAI, LiteLLM, local endpoint, Chrome, AFM, MLX, or
  llama.cpp adapter selection behavior.
- Live Ollama, vLLM, LM Studio, or llama.cpp server calls in unit tests.

## Architecture and data flow

```text
caller config + private API key
        |
        v
URL/identity/capability admission
        |
        v
explicit sync/async transport
        |  list_models (health)
        |  create_response (verified service_model_id)
        v
OpenAICompatibleExternalAdapter
        |
        v
DARExternalAdapterFacade -> existing executor/tool coordinator
```

The adapter owns configuration admission and transport translation. The
external façade remains authoritative for protocol validation, request context,
deadlines, cancellation, limits, single-use dispatch, response shaping, and
tool-call re-entry. The transport never receives a tool handler, approval
object, registry, or executor callback.

The adapter maps the façade-admitted `model_alias` to the verified
`service_model_id` exactly once. The transport sends that service ID and
returns the normalized `ModelResponse`; it does not repeat façade JSON-schema,
metadata, or tool validation. Because health is synchronous and may perform
I/O, the async façade path must offload health through the same bounded worker
used for sync adapter calls; this is an internal façade implementation change,
not a protocol change.

The default transport uses a package-owned explicit HTTP/SDK factory seam. The
seam must construct the official client with explicit `base_url`, caller-
supplied key (or intentional no-key local mode), timeout, redirect, proxy, and
cancellation settings. It must not call `create_default_openai_provider(...)`,
consult ambient auth, or silently fall back to LiteLLM. A WP3 discovery gate
decides whether `openai_client.py` can expose those controls without changing
its default path; otherwise the new module owns the small explicit client
factory. Injected transports are the only test path.

## Contracts and data model

### Public configuration

Implement the approved semantic shape:

- `adapter_id`
- `base_url`
- `model_alias`
- `service_model_id`
- `canonical_model_id`
- `tool_calling` (default false)
- `timeout_seconds` bounded to `(0, 120]`

The API key is a separate factory argument held only in a private adapter or
transport field. It must not be readable through config representation,
equality/hash, descriptors, receipts, traces, exceptions, diagnostics, or
serialization.

### Transport protocols

Define separate narrow sync and async transport/adapter variants with:

- `list_models(timeout_seconds)` returning a finite sequence of string model
  IDs; and
- `create_response(request, deadline_monotonic, cancellation)` returning the
  normalized DAR response shape.

Health is config-timeout-bounded and context-independent because v1's
`health()` method has no request context. The sync variant exposes a normal
`def create_response`; the async variant exposes `async def create_response`.
The façade offloads sync work in async workflows and rejects the async variant
from sync dispatch. Async cancellation cancels the task; sync late results are
discarded by the façade while the worker remains occupied until the underlying
call returns.

### Descriptor and health

Build the v1 descriptor with the configured adapter/model identity, fixed
provider ID `openai-compatible-external`, text-only modalities, structured
output backed by DAR-side JSON validation, and optional model-returned tool
calling. `health()` performs one bounded model-inventory operation using the
configured timeout, independent of caller request context, and admits only an
exact `service_model_id` match.

### URL policy

Validate and canonicalize before transport construction:

- allow HTTPS;
- allow HTTP only for loopback IP literals;
- reject userinfo, query, and fragment components;
- disable redirects or require same-origin redirects; and
- disable ambient proxy routing.

Keep the policy in one private validator so every factory path shares the same
admission behavior.

## Milestones and work packages

### M1 — Lock the executable boundary with RED tests

Dependencies: none.

Deliverables:

- focused tests for configuration, URL policy, identity, health, transport
  calls, secret redaction, capability denial, and sync/async cancellation;
- black-box tool-coordinator tests proving returned calls re-enter DAR once and
  the adapter has no handler or executor reference.

Exit gate: tests fail for the absent adapter and identify the exact public
contracts to implement.

### M2 — Implement admission and transport contracts

Dependencies: M1; uses existing request/response seams without changing the
default provider path.

Deliverables:

- config and URL validators;
- private secret handling;
- sync/async transport protocols and mode-specific adapter factories;
- bounded model inventory and service-model identity checks;
- timeout/deadline/cancellation and redacted error translation.

Exit gate: focused transport/admission tests pass with fake transports and no
ambient provider construction.

### M3 — Implement explicit transports and the external protocol adapter

Dependencies: M2.

Deliverables:

- discovery spike: prove whether `openai_client.py` can supply explicit
  timeout, no-proxy, redirect, cancellation, and no-key local-client controls
  without changing its default path; otherwise keep the client factory in the
  new module;
- explicit official-SDK/HTTP sync and async transports with recorded settings;
- `OpenAICompatibleExternalAdapter` (or final approved name);
- descriptor and health projection;
- request translation using existing DAR request/response helpers;
- structured-output validation and model-returned tool-call normalization;
- façade compatibility and strict single-model selection.

Exit gate: protocol conformance, tool re-entry, pre-dispatch denial, and
post-dispatch failure classification tests pass.

### M4 — Expose and document the additive migration path

Dependencies: M3.

Deliverables:

- package-root exports for config/factories;
- README example replacing a direct local endpoint adapter with strict external
  adapter coverage;
- explicit documentation that service lifecycle remains caller-owned and that
  the registry/CLI path is deferred.

Exit gate: import/API tests and documentation hooks pass; existing local
endpoint helpers remain unchanged.

### M5 — Regression and release evidence

Dependencies: M4.

Deliverables:

- focused validation record in `validation.md`;
- full root test/lint/build evidence;
- plan/spec/task consistency review before implementation handoff closure.

Exit gate: all required commands pass, no live service calls occur in tests,
and the legacy OpenAI/LiteLLM regression floor remains green.

## Work-package dependency map

| Package | Concrete responsibility | Touch points | Dependencies | Evidence |
| --- | --- | --- | --- | --- |
| WP1 | Write RED boundary tests | `tests/test_openai_compatible_external.py` | none | failing focused pytest run |
| WP2 | Add config, URL, identity, secret, and transport contracts | new external adapter module | WP1 | focused fake-transport pytest |
| WP3 | Add sync/async explicit transport implementations | new module; `openai_client.py` seams only if required | WP2 | no-default-provider and timeout/cancel tests |
| WP4 | Add protocol adapter and coordinator re-entry | new module; `external_adapter.py`; executor/coordinator tests | WP3 | conformance/tool-boundary pytest |
| WP5 | Export and document caller migration | `__init__.py`, `README.md` | WP4 | import tests and Markdown hooks |
| WP6 | Record validation and run regressions | `validation.md` | WP5 | full pytest, Ruff, build, pre-commit |

WP1 owns RED tests, WP2 owns admission and contracts, and WP3 owns the
transport discovery gate plus concrete transports. WP4 must name the existing
executor/coordinator seam and prove one complete tool re-entry cycle. WP5 and
WP6 are sequential release gates.

## Verification strategy

| Requirement | Test/check | Command |
| --- | --- | --- |
| Config and URL admission | valid HTTPS/loopback HTTP plus rejected userinfo/query/fragment, non-loopback HTTP, and unsupported schemes | `poetry run pytest tests/test_openai_compatible_external.py -q` |
| Exact identity and health | fake inventories with exact, missing, duplicate, and malformed IDs | `poetry run pytest tests/test_openai_compatible_external.py -q` |
| No ambient provider/fallback | monkeypatched default-provider constructors, no-key/no-env-auth case, and recorded transport origin/model | `poetry run pytest tests/test_openai_compatible_external.py -q` |
| HTTP safety controls | recorded client-factory settings prove timeout, `trust_env=False`/no proxy, redirect policy, and auth-free local construction | `poetry run pytest tests/test_openai_compatible_external.py -q` |
| Secret/error redaction | secret-bearing fake exceptions, repr, traces, and response metadata | `poetry run pytest tests/test_openai_compatible_external.py -q` |
| Sync/async timeout and cancellation | separate sync/async mode tests; health offload/non-blocking async path; async task cancellation; sync late-result discard and worker-capacity behavior | `poetry run pytest tests/test_openai_compatible_external.py -q` |
| Structured output | valid/invalid JSON Schema response normalization | `poetry run pytest tests/test_openai_compatible_external.py -q` |
| Tool boundary | actual executor/coordinator path: returned tool call, approval/lifecycle/tracing, exactly-once handler, follow-on request; adapter receives no handler/approval/registry | `poetry run pytest tests/test_openai_compatible_external.py tests/test_executor.py -q` |
| Existing runtime compatibility | external protocol, OpenAI client, executor, and CLI regressions | `poetry run pytest tests/test_external_adapter_protocol.py tests/test_openai_client.py tests/test_executor.py tests/test_cli.py -q` |
| Whole repository | full tests and static checks | `poetry run pytest -q` and `poetry run ruff check src tests` |
| Artifact/docs hygiene | package build and concrete changed-file hooks | `poetry build` and `poetry run pre-commit run --files specs/openai-compatible-external-adapter/spec.md specs/openai-compatible-external-adapter/plan.md specs/README.md` |

Failures in admission, identity, redaction, tool isolation, or regression
tests block progression. Live service compatibility, provider-native schema
enforcement, and service lifecycle are explicit out-of-scope residual risks.

## Migration, compatibility, and rollback

The migration is additive. Existing `create_local_openai_adapter(...)`,
OpenAI, LiteLLM, Chrome, AFM, MLX, and llama.cpp paths remain available and
unchanged. A caller opts into the new factory and passes the resulting protocol
adapter through strict model-adapter coverage.

Rollback is a configuration-level removal: stop constructing the new factory
and retain the existing endpoint adapter. No state migration, registry receipt,
model-file move, dependency removal, or destructive cleanup is permitted in
this slice.

## Risk register

| Risk | Impact | Trigger | Mitigation / rollback |
| --- | --- | --- | --- |
| Existing client lacks cancellable sync I/O | late work consumes bounded workers | blocking fake or SDK call exceeds deadline | bound worker usage, discard late result, never retry; keep existing endpoint path |
| Service model inventories differ | false unavailable or identity drift | malformed/nonstandard `/models` response | accept only the documented finite ID shape; require a separately authorized compatibility probe |
| Secret leaks through SDK exceptions | credential disclosure | fake exception contains key/URL | central redaction tests at health and generation boundaries; reject release on failure |
| Provider-native tool/schema behavior varies | behavioral mismatch | service rejects tools or schema options | advertise only configured tool capability; validate JSON in DAR; classify post-dispatch failures |
| Scope expands into registry/plugin configuration | protocol churn and unsafe credential persistence | request for install/remove or dynamic models | stop and open a separate protocol/spec slice |
| New adapter changes legacy paths | regression in existing callers | focused OpenAI/executor failures | additive module, explicit provider construction, full regression gate, configuration rollback |

## Rejected alternatives

- **Separate Ollama, vLLM, LM Studio, and llama.cpp adapters** — duplicates one
  wire contract and creates unsupported provider-specific claims.
- **Use `create_default_openai_provider(...)`** — permits ambient auth and
  LiteLLM/default fallback, violating the approved boundary.
- **Extend the receiver registry now** — protocol v1 has no safe dynamic config
  binding for endpoint, credential, and model selection.
- **Modify the existing local endpoint adapter in place** — would change a
  stable caller path and couple legacy configuration to the new protocol.
- **Add live service tests to the first slice** — non-deterministic, credential-
  bearing, and outside the approved unit-test boundary.

## Review record

- 2026-09-23 Council architecture triad (Aristotle, Ada, Feynman): first pass
  **not ready**. The valid findings were the health-context mismatch, ambiguous
  sync/async façade mode, unsupported SDK transport-control claims, duplicated
  normalization ownership, insufficient executor-level tool proof, and
  placeholder verification commands. A stale identity/configuration objection
  was rejected because the approved spec already has mandatory
  `service_model_id`, separate API-key input, and no `service_family` field.
- 2026-09-23 Council challenge round: all three reviewers agreed the plan had
  to select bounded config-timeout health, separate façade-compatible sync and
  async variants, a concrete explicit SDK/HTTP factory seam, and observable
  tests for no-auth, proxy/redirect, cancellation, and executor re-entry.
- 2026-09-23 Ponytail review: removed redundant discovery wording, replaced
  placeholder commands, kept one adapter module and one transport boundary,
  and avoided new registry or provider-family abstractions.
- Current disposition: findings addressed; ready for plan approval. No
  `tasks.md` has been created.

## Plan approval

- Status: approved by user; task breakdown created in `tasks.md`
- Notes: implementation remains gated on the TDD RED checkpoint and the
  discovery gate for explicit SDK/HTTP controls.
