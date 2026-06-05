# Progress

## Working

- The OpenAI-compatible provider-wrapper Slice 3 implementation is complete in
  `bc1ce39` (`feat(openai-client): route default adapters through providers`).
- That implementation updated `src/dynamic_agent_runner/openai_client.py` so:
  - `OpenAIClientAdapter` lazily resolves its default client through
    `create_default_openai_provider(...)`
  - `AsyncOpenAIClientAdapter` lazily resolves its default client through
    `create_default_async_openai_provider(...)`
  - both default and explicit-provider adapter paths now consistently depend on
    the repository-owned provider seam while preserving `models` / `is_local`
- Slice 3 validation passed with:
  - `poetry run pytest tests/test_openai_client.py -q` (`22 passed`)
  - `poetry run pytest tests/test_executor.py -q` (`49 passed`)
  - focused `pre-commit run --files src/dynamic_agent_runner/openai_client.py`
    `tests/test_openai_client.py`
- The provider-wrapper spec docs are now aligned through Slice 3 in `1e92aa3`
  (`docs(specs): align provider wrapper docs with slice 3`), updating:
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/openai-compatible-provider-wrapper/plan.md`
  - `specs/openai-compatible-provider-wrapper/tasks.md`
  so they match the committed adapter/provider seam implementation state and set
  Slice 4 as the next planned step.
- The OpenAI-compatible provider-wrapper Slice 2 implementation is complete in
  `282b93d` (`feat(openai-client): isolate sdk-backed provider defaults`).
- That implementation added SDK-backed default provider wrapping in
  `src/dynamic_agent_runner/openai_client.py` via:
  - `SDKBackedOpenAIClientProvider`
  - `SDKBackedAsyncOpenAIClientProvider`
  - `create_default_openai_provider(...)`
  - `create_default_async_openai_provider(...)`
  - provider-config-aware default sync/async client factories with `base_url`
    plus optional `api_key`
- Slice 2 validation passed with:
  - `poetry run pytest tests/test_openai_client.py -q` (`20 passed`)
  - `poetry run pytest tests/test_executor.py -q` (`49 passed`)
  - focused `pre-commit run --files src/dynamic_agent_runner/openai_client.py`
    `tests/test_openai_client.py`
    `specs/openai-compatible-provider-wrapper/tasks.md`
- The OpenAI-compatible provider-wrapper Slice 1 implementation is complete in
  `99e225f` (`feat(openai-client): add provider facade seam`).
- That implementation added a repository-owned provider/client facade seam in
  `src/dynamic_agent_runner/openai_client.py` via:
  - `OpenAIProviderConfig`
  - `OpenAIClientProvider`
  - `AsyncOpenAIClientProvider`
  - sync/async adapter support for lazy provider-backed client construction
- Slice 1 validation passed with:
  - `poetry run pytest tests/test_openai_client.py -q` (`13 passed`)
  - `poetry run pytest tests/test_executor.py -q` (`49 passed`)
  - focused `pre-commit run --files src/dynamic_agent_runner/openai_client.py`
    `tests/test_openai_client.py`
    `specs/openai-compatible-provider-wrapper/tasks.md`
- The OpenAI-compatible provider-wrapper plan was refreshed and committed in
  `1e6d37d` (`docs(specs): prioritize provider wrapper implementation`).
- That planning refresh updated `specs/openai-compatible-provider-wrapper/plan.md`
  with:
  - ROI framing for the feature
  - priority tiers across Slices 1 through 7
  - a smallest useful kickoff slice
  - a phased implementation order from facade work through validation/polish
- The governing main-spec backlog is still unchanged: `OA11` remains the only
  active remaining upstream-conditional follow-up in
  `specs/dynamic-agent-runner/tasks.md`.
- User direction has selected the provider-wrapper feature as the next
  high-ROI future expansion, and Slices 1-3 are now committed while Slice 4 is
  the next logical provider-wrapper implementation step.
- The primary spec set and related feature specs are now internally consistent
  with the current repo state in commit `e6b5f2c`
  (`docs(specs): align spec artifacts with repo state`).
- OA8 is implemented as a metadata-only async-session policy seam, while the
  dedicated feature-spec package now captures future expansion beyond that
  baseline.
- The new OA8 artifact set is committed across:
  - `e0b444a` — main spec/planning docs now link OA8 to the feature-spec package
  - `7e01902` — async-session memory pipeline feature-spec package
  - `b776ad0` — spec docs aligned with the implemented metadata seam
  - `0a5d59d` — user-facing docs document the async-session metadata seam
- The broader spec-alignment pass in `e6b5f2c` updated:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/plan.md`
  - `specs/dynamic-agent-runner/tasks.md`
  - `specs/openai-compatible-provider-wrapper/`
  - `specs/llm-step-interpreter-middleware/spec.md`
  so the spec artifacts now match the implemented package-directory-first API,
  current CLI contract, metadata-only seams already preserved in code, and the
  real implementation status of proposed follow-up features.
- The follow-up non-spec docs pass is complete in `e9a32d5`
  (`docs: update package-first usage examples`), updating:
  - `docs/files/quickstart.rst`
  - `docs/files/runtime-policies.rst`
  so the quickstart examples use `package_directory` / `--package`, and runtime
  policy docs describe the implemented model-selection order.
- The next active follow-up slice is `OA11`.

## Major Completed Milestones

- Core runtime foundation is complete:
  - loader and validation engine
  - repository-owned tool registry
  - OpenAI adapter boundary
  - workflow executor and CLI
  - all-pattern hello-world fixture coverage
- Runtime hardening is complete:
  - Slice 8 retry/resilience
  - Slice 9 output contracts and route validation
  - Slice 10 token budgeting
  - Slice 11 tracing/observability hooks
  - Slice 12 runtime behavior overrides
  - Slice 13 prompt-cache intent/telemetry
- Evaluation follow-up milestones are complete through:
  - execution context (`38929f1`)
  - stricter tool schema validation (`44b0847`)
  - tool exposure and policy metadata (`61f1548`)
  - richer tool result facets (`815f55a`)
  - tool lifecycle trace events (`bcd76d4`)
  - lifecycle hooks (`bf18554`)
  - model capabilities metadata (`13c6dac`)
  - concurrent run correlation (`2e45888`)
  - async-first execution through E14 Slice I.7 (`7990503`)
- Runtime-package simplification S1-S5 is complete through `84dfd31`, including:
  - grouped manifest support
  - prepared execution planning
  - prepared model-input staging
  - tool provenance metadata
  - placeholder-safe Power-Marimo fixture coverage
- Package-alignment P1-P5 is complete through `7e9a33e`, including:
  - package-directory loading
  - bundled-asset validation
  - compiled workflow layering
  - package-directory-first API/CLI contracts
  - newer upstream runtime-package taxonomy alignment
- OpenAI Agents SDK Python follow-ups completed so far:
  - OA1 guardrail metadata preservation (`a834a90`)
  - OA2 tool provenance origins (`d2cc6b2`)
  - OA3 prepare-model-input stage (`093ab47`)
  - OA4 + E9 MCP registry/lifecycle metadata (`20f20d1`)
  - E11 file-context prompt preparation (`3cdc7e9`)
  - OA5 tool-use completion metadata (`3d33bbb`)
  - OA6 handoff vs agent-as-tool metadata (`d5f4114`)
  - OA7 approval interruption metadata (`ce85a55`)
  - OA8 async-session metadata seam (`implemented in code/tests; docs aligned in
    follow-up consistency pass`)
  - OA10 sandbox/workspace runtime metadata (`540f56a`)
  - OA9 optional `tool_from_function(...)` helper (`c181328`)
- OA8 future-expansion spec package added in `7e01902`, including:
  - a light future feature spec
  - a Power-Marimo readiness decision memo
  - a host-managed multi-call continuity sketch
  - a metadata-only implementation plan
  - packaged summaries of the most relevant external references

## In Flight

- The active ordered backlog is: `OA11`.
- The active provider-wrapper follow-up, if resumed, is Slice 4.

## Remaining

- If the provider-wrapper follow-up is implemented next, continue with Slice 4
  in `specs/openai-compatible-provider-wrapper/tasks.md`: preserve
  repository-owned request construction and response normalization so provider-
  transport changes do not leak semantics into executor logic.
- Start the next scoped implementation from `OA11` in the governing SDD docs.
- If OA8 expansion is later prioritized, treat the current future-spec package
  as the design baseline and preserve the already-implemented metadata-only seam
  as the first-pass contract.
- Keep extending the runner through package-owned interfaces rather than broad
  framework expansion.
- Continue using fake-client/fake-tool tests for unit coverage.
- Refresh the memory bank after each meaningful implementation milestone.

## Risks or Follow-ups

- More advanced runtime behavior remains deferred until explicitly selected:
  approval/resume engines, sessions, broader MCP integration, sandbox/workspace
  runtime execution, and iterative agent-loop semantics.
- OA8 currently exists as a **protocol-design seam** in the runtime, but it does
  not yet provide runner-owned memory storage, replay, or automatic session
  continuation behavior.
- `parallel_join`, `parallel_fanout`, and broader multi-agent execution remain
  unsupported runtime behavior.
- RAG/GraphRAG, portable tool taxonomy, handoffs, and agent-as-tool support are
  currently metadata/validation surfaces, not full runtime execution engines.
- Local llama.cpp and graph-mutation work remains feature-spec-only, with no
  active runtime implementation in the codebase.
