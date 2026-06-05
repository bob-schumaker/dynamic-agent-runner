# Progress

## Working

- The authoritative llama.cpp local-model Slice 1 implementation is now active
  progress rather than a future-only spec area.
- Slice 1 is complete through T1.4:
  - `a5798cc` — T1.1 RED helper-contract tests
  - `b79f124` — T1.2 RED executor-routing tests
  - `6d269ad` — T1.3 helper implementation
  - `ee0bf33` — T1.4 provider-seam wiring
  - `22cc09b` — authoritative spec/plan/tasks/validation refresh through T1.4
- The resulting first-slice local endpoint helper state now includes:
  - `src/dynamic_agent_runner/local_models.py`
  - `LocalOpenAIEndpointConfig`
  - `create_local_openai_adapter(...)`
  - `create_local_async_openai_adapter(...)`
  - provider-config translation that routes adapter construction through
    repository-owned helper factories in
    `src/dynamic_agent_runner/openai_client.py`
- Focused validation for the latest local-model implementation step passed with:
  - `poetry run pytest tests/test_openai_client.py -q 2>&1`
    (`29 passed in 0.15s`)
  - `poetry run pytest tests/test_executor.py -q 2>&1`
    (`50 passed in 0.38s`)
- A focused primary-vs-feature spec consistency audit is complete in `3f61d99`
  (`docs(specs): reconcile primary spec with provider wrapper state`).
- That follow-up updated `specs/dynamic-agent-runner/spec.md` so the main
  product spec no longer describes the OpenAI-compatible provider-wrapper seam
  as future work. Instead, it now records the provider boundary as resolved and
  aligned with the implemented provider-wrapper feature spec state.
- Focused validation for that audit passed with:
  - `pre-commit run --files specs/dynamic-agent-runner/spec.md`
    `specs/dynamic-agent-runner/plan.md`
    `specs/dynamic-agent-runner/tasks.md`
    `specs/async-session-memory-pipeline/spec.md`
    `the then-current local-model/graph-mutation future spec`
    `specs/llm-step-interpreter-middleware/spec.md`
    `specs/openai-compatible-provider-wrapper/spec.md`
    `specs/openai-compatible-provider-wrapper/plan.md`
    `specs/openai-compatible-provider-wrapper/tasks.md`
  - all targeted spec files passed `rumdl check` / `rumdl format`
- The OpenAI-compatible provider-wrapper Slice 6 implementation is complete in
  `66212f4` (`feat(openai-client): export provider config seam`).
- That implementation updated the package-level public surface so:
  - `src/dynamic_agent_runner/__init__.py` now re-exports
    `OpenAIProviderConfig`
  - `src/dynamic_agent_runner/__init__.py` now re-exports
    `create_default_openai_provider(...)` and
    `create_default_async_openai_provider(...)`
  - `tests/test_import.py` now verifies those public exports exist
  - `README.md` now includes a package-level OpenAI-compatible endpoint example
    that preserves the existing `model_adapter` seam
- Slice 6 validation passed with:
  - `poetry run pytest tests/test_import.py -q` (`1 passed`)
  - focused `pre-commit run --files src/dynamic_agent_runner/__init__.py`
    `tests/test_import.py` `README.md`
- The provider-wrapper spec docs are now aligned through Slice 6 in `556694e`
  (`docs(specs): align provider wrapper docs with slice 6`), updating:
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/openai-compatible-provider-wrapper/plan.md`
  - `specs/openai-compatible-provider-wrapper/tasks.md`
  so they match the committed provider-wrapper implementation state, public
  export surface, and focused import-validation evidence.
- The OpenAI-compatible provider-wrapper Slice 4 implementation is complete in
  `a437b1a` (`feat(openai-client): centralize response dispatch helpers`).
- That implementation updated `src/dynamic_agent_runner/openai_client.py` so:
  - `create_openai_response(...)` centralizes sync transport dispatch,
    runtime-facing `ModelExecutionError` translation, and
    `normalize_openai_response(...)` use
  - `create_async_openai_response(...)` centralizes the async equivalent
  - `OpenAIClientAdapter` and `AsyncOpenAIClientAdapter` now route through those
    repository-owned helpers instead of inlining transport/normalization logic
- Slice 4 validation passed with:
  - `poetry run pytest tests/test_openai_client.py -q` (`24 passed`)
  - `poetry run pytest tests/test_executor.py -q` (`49 passed`)
  - focused `pre-commit run --files src/dynamic_agent_runner/openai_client.py`
    `tests/test_openai_client.py`
- The provider-wrapper spec docs are now aligned through Slice 4 in `14fa1ea`
  (`docs(specs): align provider wrapper docs with slice 4`), updating:
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/openai-compatible-provider-wrapper/plan.md`
  - `specs/openai-compatible-provider-wrapper/tasks.md`
  so they match the committed provider-wrapper implementation state and set
  Slice 5 as the next planned step.
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
- `OA11` is now complete in `1d0aa32`
  (`feat(registry): add portable tool type metadata`).
- That implementation added an upstream-aligned portable `tool_type` seam so:
  - `src/dynamic_agent_runner/models.py` now defines `ToolType` and preserves
    `ToolDefinition.tool_type` separately from runtime-specific `adapter` and
    provenance/source metadata
  - `src/dynamic_agent_runner/validation.py` now fails closed for unsupported
    `tool_type` values in manifest and tool-index tool definitions
  - `src/dynamic_agent_runner/registry.py` now records portable `file_read`
    semantics for the built-in `local_workspace` tool pack
  - `src/dynamic_agent_runner/__init__.py` now exports `ToolType`
  - focused tests now cover import, registry, built-in-pack, and validation
    behavior for `tool_type`
- OA11 implementation validation passed with:
  - `poetry run pytest tests/test_import.py tests/test_registry.py`
    `tests/test_validation.py -q 2>&1` (`86 passed`)
  - focused `pre-commit run --files src/dynamic_agent_runner/__init__.py`
    `src/dynamic_agent_runner/models.py`
    `src/dynamic_agent_runner/registry.py`
    `src/dynamic_agent_runner/validation.py`
    `tests/test_import.py` `tests/test_registry.py` `tests/test_validation.py`
- The OA11 spec-doc alignment is complete in `ac422b0`
  (`docs(specs): record OA11 tool type alignment`), updating:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/plan.md`
  - `specs/dynamic-agent-runner/tasks.md`
  so the primary spec package now records the upstream-confirmed `tool_type`
  seam and marks the original OA follow-up queue complete.
- OA11 spec-doc validation passed with:
  - `pre-commit run --files specs/dynamic-agent-runner/spec.md`
    `specs/dynamic-agent-runner/plan.md`
    `specs/dynamic-agent-runner/tasks.md`
  - all targeted spec files passed `rumdl check` / `rumdl format`
- User direction selected the provider-wrapper feature as the next high-ROI
  future expansion, and Slices 1-6 are now committed.
- The primary spec set and related feature specs are now internally consistent
  with the current repo state in commit `e6b5f2c`
  (`docs(specs): align spec artifacts with repo state`).
- The later focused audit in `3f61d99` reconciled the one remaining stale
  provider-wrapper reference in the main spec, so the audited primary spec and
  current feature-spec packages are now aligned on that feature's implemented
  status.
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
- The original OA follow-up slice queue is complete through OA11.

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

- The active ordered backlog has no remaining OA slice; the currently active
  implementation track is the llama.cpp local-model feature under
  `specs/llama-cpp-local-model/`.
- The current execution gate for that feature is T1.5: export any approved
  caller-visible local helper or config type from the package root and validate
  it with `poetry run pytest tests/test_import.py -q`.
- The provider-wrapper follow-up is complete through Slice 6; any further work
  there would now be optional polish or broader provider-specific follow-up.

## Remaining

- Complete llama.cpp local-model Slice 1 from the authoritative task list,
  beginning with T1.5 package-root export work and then any later Slice 1
  follow-up validation/docs steps that become necessary.
- If the provider-wrapper area is resumed, treat it as optional follow-up work
  rather than a required next slice; any new work should preserve fake-client
  testing and avoid live network calls.
- Start the next scoped implementation from a newly selected follow-up in the
  governing SDD docs; OA11 is already complete.
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
- RAG/GraphRAG, handoffs, and agent-as-tool support are currently
  metadata/validation surfaces, not full runtime execution engines. Portable
  tool taxonomy is now implemented as a metadata/validation seam through OA11.
- The old combined llama.cpp and graph-mutation future-spec area is now split
  into two authoritative feature specs:
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/internal-graph-mutation/spec.md`
  The graph-mutation area still has no active runtime implementation, while the
  llama.cpp local-model area is now implemented through Slice 1 T1.4 only.
- The llama.cpp local-model spec has since been tightened against upstream
  `llama-cpp-python` docs/README/examples and the local `huggingface_hub`
  checkout so that future implementation now explicitly assumes:
  - caller/deployer-owned OpenAI-compatible local server endpoints rather than
    runtime-managed server launch
  - adapter-supported Hugging Face model download when referenced assets are
    missing locally
  - an optional adapter model-cache folder with default path
    `~/.ollama/models`
- Council review of `specs/llama-cpp-local-model/spec.md` was completed and the
  spec was updated accordingly. The current llama.cpp local-model direction now
  also explicitly records:
  - a preferred first implementation path of caller/deployer-provided
    OpenAI-compatible endpoints over in-process integration
  - supported runtime-owned model reference shapes for local path, Hub file, and
    Hub snapshot resolution
  - model-resolution precedence of explicit local path, explicit cache lookup,
    default `~/.ollama/models` lookup, then explicit Hub download
  - separate failure boundaries for model-resolution errors versus endpoint
    connectivity/protocol errors
- A later three-round debate review then tightened the same llama.cpp spec so
  the future contract now also explicitly states:
  - the expected first implementation slice uses the existing OpenAI-compatible
    adapter/provider seam with runtime-owned provider config and normal adapter
    metadata rather than requiring a new llama-specific wrapper first
  - endpoint-backed local chat may ship before separate local embedding
    execution, while preserving the later embedding contract for pruning-related
    work
  - offline or no-network policy for model download/resolution is owned by
    caller/deployment runtime configuration above the portable workflow package
  - model mismatch reporting keys off runtime-owned adapter identity such as
    declared model alias, explicit local path, or explicit Hugging Face
    reference
- The llama.cpp local-model future feature now has an authoritative SDD spec in
  commit `1fdfdda` (`docs(specs): make llama.cpp local-model spec
  authoritative`). That refresh converted the feature doc from light-mode
  framing into a guided SDD spec with explicit user stories, non-functional
  requirements, scope boundaries, dependencies/assumptions, and a next-gate
  requirement that planning artifacts exist before implementation.
- Focused validation for that authoritative-spec refresh passed with:
  - `pre-commit run --files specs/llama-cpp-local-model/spec.md 2>&1`
  - `rumdl check` / `rumdl format` passed after one markdown line-wrap fix
- The next SDD gate for the same feature is now committed in `82c62fe`
  (`docs(specs): add llama.cpp local-model planning artifacts`), adding:
  - `specs/llama-cpp-local-model/plan.md`
  - `specs/llama-cpp-local-model/tasks.md`
- That planning pass established:
  - Slice 1 = endpoint-backed local chat through the existing provider seam
  - Slice 2 = runtime-owned model-reference resolution and failure taxonomy
  - Slice 3 = optional embedding / in-process follow-up
  - a new expected helper surface in `src/dynamic_agent_runner/local_models.py`
    instead of a new executor path
  - explicit test-first tasks and validation commands for the first slice
- Focused validation for the new planning artifacts passed with:
  - `pre-commit run --files specs/llama-cpp-local-model/plan.md`
    `specs/llama-cpp-local-model/tasks.md` `2>&1`
  - `rumdl check` / `rumdl format` passed
- Subsequent implementation progress for that feature is now complete through:
  - T1.1 RED in `a5798cc`
  - T1.2 RED in `b79f124`
  - T1.3 GREEN in `6d269ad`
  - T1.4 GREEN in `ee0bf33`
  - docs/validation refresh through T1.4 in `22cc09b`
- The current next gate for that feature is T1.5 package-root export work.
