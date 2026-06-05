# Active Context

## Current Focus

- The OpenAI-compatible provider-wrapper feature plan was reprioritized and
  expanded in commit `1e6d37d`
  (`docs(specs): prioritize provider wrapper implementation`). The updated
  `specs/openai-compatible-provider-wrapper/plan.md` now records ROI framing,
  priority tiers across the full feature scope, a smallest useful kickoff slice,
  and a phased implementation order from facade work through validation/polish.
- The primary spec and feature spec set were refreshed for internal consistency
  and repo-state accuracy, then committed in `e6b5f2c`
  (`docs(specs): align spec artifacts with repo state`).
- User-facing non-spec docs examples were refreshed and committed in `e9a32d5`
  (`docs: update package-first usage examples`) so the quickstart and runtime
  policy docs now match the package-directory-first API/CLI contract.
- The runtime is implemented through package-alignment Slice P5, E14 async-first
  execution, OA7 deferred approval interruption metadata preservation, OA10
  deferred sandbox/workspace runtime metadata preservation, OA9
  `tool_from_function(...)` helper support, and OA11 portable `tool_type`
  metadata alignment.
- OA8 is already implemented as a metadata-only async-session policy seam, while
  the repository-local feature-spec package under
  `specs/async-session-memory-pipeline/` captures future expansion beyond that
  baseline.
- User-facing docs are now aligned with that OA8 baseline in `README.md` and
  `docs/files/runtime-policies.rst` via commit `0a5d59d`.
- OA11 landed in commit `1d0aa32`
  (`feat(registry): add portable tool type metadata`), aligning the runtime with
  the upstream `tool_type` manifest field from the agent-runtime-package
  reference.
- The OA11 spec-doc refresh landed in commit `ac422b0`
  (`docs(specs): record OA11 tool type alignment`), updating the main
  spec/plan/task package to record the implemented seam and mark the original OA
  follow-up queue complete.
- There is no remaining active OA slice in the original follow-up sequence; the
  current remaining work is back to future scoped follow-ups and promoted
  evaluation-driven expansions.
- User direction has now selected the OpenAI-compatible provider-wrapper feature
  as the highest-ROI future expansion. Slice 1 landed in commit `99e225f`
  (`feat(openai-client): add provider facade seam`), and Slice 2 landed in
  commit `282b93d` (`feat(openai-client): isolate sdk-backed provider
  defaults`). Together those slices introduced the repository-owned
  provider/client facade seam, provider configuration, SDK-backed default
  provider wrappers, and provider-config-aware default sync/async client
  factories with `base_url` plus optional `api_key` support.
- The provider-wrapper spec docs were refreshed after Slice 2 in commit
  `5dce42b` (`docs(specs): align provider wrapper docs with slice 2`) so
  `specs/openai-compatible-provider-wrapper/spec.md` and
  `specs/openai-compatible-provider-wrapper/plan.md` now describe Slices 1-2 as
  implemented and keep Slice 3 as the next planned implementation step.
- Provider-wrapper Slice 3 landed in commit `bc1ce39`
  (`feat(openai-client): route default adapters through providers`). That slice
  refactored `OpenAIClientAdapter` and `AsyncOpenAIClientAdapter` so their
  default lazy-construction paths now resolve clients through the repository-
  owned default provider facades instead of bypassing the provider seam.
- The provider-wrapper spec docs were refreshed again after Slice 3 in commit
  `1e92aa3` (`docs(specs): align provider wrapper docs with slice 3`) so the
  feature-spec package now records Slices 1-3 as implemented and advances the
  next planned step to Slice 4.
- Provider-wrapper Slice 4 landed in commit `a437b1a`
  (`feat(openai-client): centralize response dispatch helpers`). That slice
  extracted repository-owned sync/async response-dispatch helpers in
  `src/dynamic_agent_runner/openai_client.py` and routed both adapters through
  those helpers so transport calls, runtime-facing error translation, and
  response normalization remain centralized inside repository-owned code.
- The provider-wrapper spec docs were refreshed again after Slice 4 in commit
  `14fa1ea` (`docs(specs): align provider wrapper docs with slice 4`) so the
  feature-spec package now records Slices 1-4 as implemented and advances the
  next planned step to Slice 5.
- Provider-wrapper Slice 6 landed in commit `66212f4`
  (`feat(openai-client): export provider config seam`). That slice re-exported
  `OpenAIProviderConfig`, `create_default_openai_provider(...)`, and
  `create_default_async_openai_provider(...)` from
  `src/dynamic_agent_runner/__init__.py`, added import-smoke coverage in
  `tests/test_import.py`, and documented a package-level compatible-endpoint
  example in `README.md`.
- The provider-wrapper spec docs were refreshed again after Slice 6 in commit
  `556694e` (`docs(specs): align provider wrapper docs with slice 6`) so the
  feature-spec package now records Slices 1-6 as implemented, records the
  import-surface validation evidence, and treats additional provider-wrapper
  work as optional future polish rather than a required next slice.
- A focused primary-spec consistency audit landed in commit `3f61d99`
  (`docs(specs): reconcile primary spec with provider wrapper state`). That
  follow-up verified the main `specs/dynamic-agent-runner/` artifacts against
  the active feature-spec packages and resolved the stale primary-spec open
  question that still described the provider-wrapper seam as future work even
  though `specs/openai-compatible-provider-wrapper/` now records it as
  implemented through Slice 6.

## Current State Snapshot

- Public runtime surface is package-directory-first:
  `load_agent_workflow(...)`, `run_agent_workflow(...)`, and
  `run_agent_workflow_async(...)` accept package-based workflow inputs, while
  lower-level artifact seams remain available.
- The executor is async-first. Sync entry points are compatibility wrappers over
  the async semantic path and reject already-running event loops.
- Core implemented seams now include:
  - grouped manifest loading (`runtime`, `metadata`, `extensions`)
  - prepared execution planning and prepared model-input staging
  - repository-owned tool registry and override handling
  - OpenAI adapter boundary with a repository-owned provider/client facade seam,
    SDK-backed default provider wrappers, and fake-client-compatible tests
  - retry, output-contract validation, token-budget preflight, tracing, and
    runtime behavior overrides
  - run-correlation support for concurrent execution
- Supported future runtime-package metadata now includes:
  - provider-neutral `model_requirements`
  - `react_loop` validation
  - `metadata.rag_pipeline`
  - `evidence_loop`
  - deferred guardrails, MCP registry/lifecycle metadata,
    approval interruption/resumable-run metadata, async-session policy metadata,
    and sandbox/workspace runtime metadata
- The OA8 design baseline now lives in a dedicated spec package:
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/async-session-memory-pipeline/decision-memo.md`
  - `specs/async-session-memory-pipeline/power-marimo-host-integration.md`
  - `specs/async-session-memory-pipeline/implementation-plan.md`
  - packaged supporting reference summaries under
    `specs/async-session-memory-pipeline/references/`

## Latest Completed Follow-up Slices

- Provider-wrapper Slice 3 completed in `bc1ce39`: `OpenAIClientAdapter` and
  `AsyncOpenAIClientAdapter` now lazily construct default clients through
  `create_default_openai_provider(...)` /
  `create_default_async_openai_provider(...)`, so both explicit-provider and
  default-construction paths consistently depend on the repository-owned
  provider seam while preserving `models` / `is_local` executor-routing
  semantics.
- Provider-wrapper Slice 4 completed in `a437b1a`: `openai_client.py` now
  exposes `create_openai_response(...)` and
  `create_async_openai_response(...)`, and `OpenAIClientAdapter` /
  `AsyncOpenAIClientAdapter` route through those repository-owned helpers so
  request kwargs, runtime-facing error translation, and response normalization
  remain centralized in the adapter boundary.
- Provider-wrapper Slice 6 completed in `66212f4`:
  `dynamic_agent_runner.__init__` now re-exports the provider-configuration
  seam (`OpenAIProviderConfig`, `create_default_openai_provider(...)`, and
  `create_default_async_openai_provider(...)`), `tests/test_import.py` now
  covers those package-level exports, and `README.md` now shows a package-level
  OpenAI-compatible endpoint example using `model_adapter`.
- Provider-wrapper Slice 6 validation passed with:
  - `poetry run pytest tests/test_import.py -q` (`1 passed`)
  - focused `pre-commit run --files src/dynamic_agent_runner/__init__.py`
    `tests/test_import.py` `README.md`
- Provider-wrapper Slice 4 validation passed with:
  - `poetry run pytest tests/test_openai_client.py -q` (`24 passed`)
  - `poetry run pytest tests/test_executor.py -q` (`49 passed`)
  - focused `pre-commit run --files src/dynamic_agent_runner/openai_client.py`
    `tests/test_openai_client.py`
- Provider-wrapper Slice 3 validation passed with:
  - `poetry run pytest tests/test_openai_client.py -q` (`22 passed`)
  - `poetry run pytest tests/test_executor.py -q` (`49 passed`)
  - focused `pre-commit run --files src/dynamic_agent_runner/openai_client.py`
    `tests/test_openai_client.py`
- Provider-wrapper Slice 2 completed in `282b93d`: `openai_client.py` now
  exposes `SDKBackedOpenAIClientProvider`,
  `SDKBackedAsyncOpenAIClientProvider`, `create_default_openai_provider(...)`,
  and `create_default_async_openai_provider(...)`, while the default sync/async
  client factories route through the provider seam and apply `base_url` plus
  optional `api_key` configuration.
- Provider-wrapper Slice 2 validation passed with:
  - `poetry run pytest tests/test_openai_client.py -q` (`20 passed`)
  - `poetry run pytest tests/test_executor.py -q` (`49 passed`)
  - focused `pre-commit run --files src/dynamic_agent_runner/openai_client.py`
    `tests/test_openai_client.py`
    `specs/openai-compatible-provider-wrapper/tasks.md`
- Provider-wrapper Slice 1 completed in `99e225f`: `openai_client.py` now
  exposes `OpenAIProviderConfig`, `OpenAIClientProvider`, and
  `AsyncOpenAIClientProvider`, and the sync/async adapters can lazily construct
  clients through that repository-owned facade while preserving the existing
  injected-client path and default lazy client construction behavior.
- Provider-wrapper Slice 1 validation passed with:
  - `poetry run pytest tests/test_openai_client.py -q` (`13 passed`)
  - `poetry run pytest tests/test_executor.py -q` (`49 passed`)
  - focused `pre-commit run --files src/dynamic_agent_runner/openai_client.py`
    `tests/test_openai_client.py`
    `specs/openai-compatible-provider-wrapper/tasks.md`
- `OA9` completed in `c181328`: the registry now exposes an optional
  `tool_from_function(...)` helper that builds `RegisteredTool` instances from
  Python callables, accepts explicit metadata when provided, and falls back to
  conservative inference for missing label, description, and input-schema
  fields using the callable name, docstring, and supported signature/type-hint
  shapes.
- OA9 validation passed with:
  `poetry run pytest tests/test_registry.py tests/test_import.py -q 2>&1`
  (`32 passed`) and scoped `poetry run pre-commit run --files ...` on the OA9
  code/spec/doc files.
- `OA10` completed in `540f56a`: deferred
  `runtime.execution_policy.sandbox_runtime` metadata is preserved on
  `RuntimeManifest` and `ExecutionPlan` without changing the current read-only
  `local_workspace` built-in tool pack or enabling a writable workspace runtime.
- OA10 validation passed with:
  `poetry run pytest tests/test_artifacts.py tests/test_validation.py -q 2>&1`
  (`66 passed`) and scoped `poetry run pre-commit run --files ...` on the OA10
  code/spec/doc files.
- `OA7` completed in `ce85a55`: deferred
  `runtime.execution_policy.approval_interruption` metadata is preserved on
  `RuntimeManifest` and `ExecutionPlan` without adding a live approval engine or
  pause/resume execution behavior.
- OA7 validation passed with:
  `poetry run pytest tests/test_artifacts.py tests/test_validation.py -q 2>&1`
  (`60 passed`) and scoped `poetry run pre-commit run --files ...` on the OA7
  code/spec/doc files.
- `OA5` completed in `3d33bbb`: deferred
  `runtime.execution_policy.tool_use_completion` metadata is preserved without
  changing executor behavior.
- `OA6` completed in `d5f4114`: grouped `metadata.handoffs`, typed node-local
  `agent_as_tool` / `agent_tool` metadata, and corresponding `ExecutionPlan` /
  `PreparedNode` preservation are in place without adding a new primitive node
  kind or changing current executor behavior.
- OA6 validation passed with:
  `poetry run pytest`
  `tests/test_artifacts.py tests/test_validation.py`
  `tests/test_executor.py tests/test_power_marimo_fixture.py -q 2>&1`
  (`106 passed`) plus scoped `pre-commit` on the changed code/spec files.

## Important Current Facts

- The source of truth for current task sequencing is:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/plan.md`
  - `specs/dynamic-agent-runner/tasks.md`
- The primary spec now explicitly treats the provider-wrapper boundary as
  resolved in commit `3f61d99`, aligning the main product spec with the
  implemented OpenAI-compatible provider-wrapper feature state.
- The spec-consistency refresh also added and aligned the follow-up feature-spec
  package at `specs/openai-compatible-provider-wrapper/` and corrected the
  future API example in
  `specs/llm-step-interpreter-middleware/spec.md` to match the current
  package-directory-first runtime contract.
- The source of truth for the current provider-wrapper follow-up is:
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/openai-compatible-provider-wrapper/plan.md`
  - `specs/openai-compatible-provider-wrapper/tasks.md`
- Provider-wrapper Slices 1-6 are now implemented and recorded in
  `specs/openai-compatible-provider-wrapper/tasks.md`.
- The provider-wrapper spec/plan/task docs are aligned through Slice 6 in
  commit `556694e`, so the feature-spec package now consistently reflects the
  committed implementation state, public export surface, and focused validation
  evidence.
- The provider-wrapper plan now explicitly prioritizes:
  - repository-owned sync/async provider-client facades
  - SDK-backed wrapper isolation
  - `base_url` plus optional `api_key` configuration
  - adapter refactoring that preserves `models` / `is_local`
  - repository-owned request/response semantics
- The source of truth for current OA8 future-expansion design is:
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/async-session-memory-pipeline/decision-memo.md`
  - `specs/async-session-memory-pipeline/power-marimo-host-integration.md`
  - `specs/async-session-memory-pipeline/implementation-plan.md`
- The source of truth for current user-facing OA8 documentation is:
  - `README.md`
  - `docs/files/runtime-policies.rst`
- The runtime intentionally remains OpenAI-first through a small adapter
  boundary; `ocihelper`, `ai-tools-core`, and `openai-tools-core` are not part
  of the intended initial runtime direction.
- Agent patterns, RAG/GraphRAG shapes, portable tool taxonomy, handoffs, and
  agent-as-tool semantics are represented as metadata layered onto the existing
  primitive runtime graph rather than as new primitive node kinds.
- `../power-marimo` remains the first downstream fit. Its `marimo-pair`
  capability is modeled as a bounded agent-as-tool/SKILL-backed operation, not a
  durable handoff or a new runtime primitive.
- The current first-customer decision for `power-marimo` is to support multi-turn
  continuity through **host-managed repeated runner calls**, not runner-owned
  durable session behavior in the near term.
- The current published-doc alignment for OA8 is:
  - spec docs aligned in `b776ad0`
  - memory-bank alignment recorded in `aec1c5d`
  - user-facing docs aligned in `0a5d59d`
- The broader spec-set alignment beyond OA8 is now recorded in `e6b5f2c`.
- The broader non-spec docs follow-up for stale package/API examples is now
  recorded in `e9a32d5`.
- `memory-bank/notes/historical-user-prompts.txt` may contain durable prompt
  history, including a newly recorded future-looking prompt about evaluating
  `/Users/roschuma/Repos/github/omlx/` as a possible mac-only local model
  feature.
- The future local-model and workflow-derivation area is now split between:
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/internal-graph-mutation/spec.md`
  Both are authoritative future-feature specs, and the runtime codebase still
  has no active implementation for either feature area.
- The llama.cpp local-model spec was further refined against the upstream
  `llama-cpp-python` docs/README/examples and the local `huggingface_hub`
  checkout. The current spec direction now says:
  - caller/deployer-owned OpenAI-compatible llama.cpp server endpoints are the
    supported server-side boundary
  - the expected first implementation slice uses the existing OpenAI-compatible
    adapter/provider seam plus runtime-owned provider config and normal adapter
    metadata such as advertised model names and `is_local=True`
  - the runtime should not launch or supervise a local llama.cpp server itself
  - missing Hugging Face-referenced model assets may be downloaded by the
    adapter via `huggingface_hub`
  - the adapter accepts an optional model-cache folder and defaults to
    `~/.ollama/models` when unspecified
  - the first implementation should prefer caller/deployer-provided
    OpenAI-compatible endpoints over in-process llama.cpp integration
  - endpoint-backed local chat may land before separate local embedding
    execution, and that later embedding work does not expand the first slice
    into graph-mutation delivery
  - model resolution now has explicit supported reference shapes and precedence:
    explicit local path, explicit cache lookup, default `~/.ollama/models`
    lookup, then explicit Hugging Face download
  - offline or no-network behavior for model download/resolution is owned by
    caller/deployment runtime configuration rather than workflow metadata
  - model-resolution failures are expected to remain distinct from endpoint
    connectivity or protocol failures
  - intended model identity for mismatch reporting comes from runtime-owned
    adapter configuration such as declared model alias, explicit local path, or
    explicit Hugging Face reference

## Next Steps

- The provider-wrapper follow-up is currently complete through Slice 6; if work
  resumes in that area, treat it as optional future polish or broader
  provider-specific follow-up rather than a required next implementation slice.
- If implementation resumes, start from `OA11` in the governing SDD artifacts.
- If OA8 expansion is later resumed, start from
  `specs/async-session-memory-pipeline/implementation-plan.md` and preserve the
  existing metadata-only seam as the first-pass contract.
- Keep new behavior behind package-owned interfaces and fail-closed validation.
- Preserve fake-client/fake-tool tests and avoid live OpenAI API calls in unit
  coverage.
- Continue treating `parallel_join`, `parallel_fanout`, live MCP execution,
  approval/resume engines, and broader multi-agent runtime behavior as deferred
  until a scoped slice explicitly selects them.
