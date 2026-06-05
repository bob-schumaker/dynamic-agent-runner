# llama.cpp Local-Model Adapter Implementation Plan

Status: Draft

## Goal

Plan a phased implementation that adds llama.cpp-oriented local-model support
through the repository's existing OpenAI-compatible adapter/provider seam,
without introducing a separate executor path or runtime-managed server
lifecycle.

## Spec Trace

- Spec: `specs/llama-cpp-local-model/spec.md`
- Related repo guardrails:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/openai-compatible-provider-wrapper/spec.md`
- Constitution: none; repository rules and the approved spec are the active
  guardrails for this feature

## Technical Summary

- The first implementation slice should add a caller-facing local-model helper
  that builds `OpenAIClientAdapter` / `AsyncOpenAIClientAdapter` instances for
  caller-owned or deployer-owned OpenAI-compatible local endpoints.
- The first slice must keep executor behavior unchanged by continuing to rely on
  advertised adapter `models` plus `is_local=True` for `local_only` routing.
- Local-model-specific configuration, reference parsing, and future asset
  resolution should live in a dedicated runtime-owned helper module rather than
  overloading `executor.py` with provider-specific behavior.
- Runtime-managed server launch, supervision, readiness, and shutdown remain
  out of scope.
- Runtime-owned model reference resolution, cache lookup, Hugging Face download,
  and optional embedding follow-up should be planned as later slices that extend
  the same local-model helper surface without changing the core executor path.

## Source Artifacts

- `specs/llama-cpp-local-model/spec.md` — authoritative feature intent and
  boundaries
- `specs/openai-compatible-provider-wrapper/spec.md` — existing provider seam
  that the first slice must reuse
- `src/dynamic_agent_runner/openai_client.py` — current adapter/provider and
  response-normalization boundary
- `src/dynamic_agent_runner/executor.py` — current model selection and
  `local_only` routing behavior
- `src/dynamic_agent_runner/errors.py` — runtime-facing error types
- `src/dynamic_agent_runner/__init__.py` — package-level exports
- `tests/test_openai_client.py` — primary adapter/provider validation surface
- `tests/test_executor.py` — executor routing validation surface
- local upstream references:
  - `/Users/roschuma/Repos/github/llama-cpp-python/`
  - `/Users/roschuma/Repos/github/huggingface_hub/`

## Current Repository State

- `openai_client.py` already owns repository-controlled request construction,
  sync/async provider facades, SDK-backed default providers, and normalized
  response handling.
- The repository now exposes an initial llama.cpp-oriented local endpoint helper
  module at `src/dynamic_agent_runner/local_models.py`, now re-exported from
  `src/dynamic_agent_runner/__init__.py` for the approved caller-facing config
  and helper surface, but it does not yet include model reference types,
  asset-resolution helpers, or a distinct local-model failure taxonomy; the
  helper routes through explicit adapter-factory helpers owned by
  `openai_client.py`.
- Existing tests already exercise fake-client adapter behavior and executor
  routing, so the new feature can extend current test surfaces without live
  infrastructure.

## Delivery Strategy

### Slice 1 — Endpoint-backed local chat through the existing provider seam

Deliver the highest-ROI path first:

- add a runtime-owned local endpoint config/helper surface
- default resulting adapters to `is_local=True`
- allow one or more caller-declared model aliases
- preserve repository-owned request construction and normalization
- prove `local_only` executor routing works without any new executor branch
- current checkpoint: T1.1 RED helper-contract tests completed in commit
  `a5798cc` (`test(local-models): add RED tests for local endpoint helpers`);
  T1.2 RED executor-routing tests completed in commit `b79f124`
  (`test(local-models): add RED executor routing coverage`); T1.3 helper
  implementation completed in commit `6d269ad`
  (`feat(local-models): add local openai endpoint helpers`); T1.4 provider-seam
  wiring completed in commit `ee0bf33`
  (`refactor(local-models): route helpers through adapter factories`); T1.5
  package-root exports completed in commit `dd37c62`
  (`feat(local-models): export local endpoint helpers`); T2.1 is the next Slice
  2 step

This slice satisfies the primary implementation path in the approved spec.

### Slice 2 — Runtime-owned model reference resolution and failure taxonomy

After the endpoint-backed chat slice is stable, extend the local-model helper
surface so it can represent:

- explicit local file paths
- explicit cache roots
- default cache lookup under `~/.ollama/models`
- explicit Hugging Face file references
- explicit Hugging Face snapshot references

This slice should also introduce a clearer runtime-facing distinction between:

- model-resolution failures
- endpoint connectivity failures
- endpoint protocol failures
- model-identity mismatch failures

This remains runtime-owned preflight and resolution logic, not server-lifecycle
ownership.

### Slice 3 — Optional embedding and in-process follow-up

Only after Slices 1 and 2 are complete should later work consider:

- separate local embedding configuration
- in-process `llama_cpp.Llama` usage
- upstream prerequisites such as `embedding=True` and chat-format-specific
  function-calling requirements

This slice must remain separate from graph-mutation delivery.

## Architectural Decision

### Chosen approach

Introduce a dedicated local-model support module that builds on the existing
OpenAI-compatible provider seam instead of introducing a new top-level model
execution family.

### Why this approach is preferred

- It preserves the current executor contract and local-routing behavior.
- It keeps provider-specific configuration out of `executor.py`.
- It creates one place to evolve local endpoint config, model references,
  resolution helpers, and optional embeddings.
- It keeps response normalization and request shaping under current repository
  ownership.

### Why a new executor path is rejected

- `executor.py` already has the right routing boundary through `models` and
  `is_local`.
- A new executor branch would duplicate existing adapter-selection behavior and
  create architectural drift from the provider-wrapper seam.

### Why runtime-managed server launch is rejected

- The approved spec keeps server installation, launch, and lifecycle above the
  library boundary.
- Server ownership would add deployment-specific behavior to a portable runtime
  library and would not improve the existing adapter-routing seam.

### Why in-process llama.cpp is not the first slice

- The approved spec prefers endpoint-backed local chat as the first delivery
  path.
- The repository already has an async-friendly OpenAI-compatible transport seam,
  while in-process integration would add a separate runtime surface earlier than
  needed.

## Affected Areas

- `src/dynamic_agent_runner/local_models.py` — new runtime-owned local-model
  config, helper, reference, and future resolution surface
- `src/dynamic_agent_runner/openai_client.py` — integration point for any local
  helper that builds existing adapters and preserves normalization ownership
- `src/dynamic_agent_runner/errors.py` — optional new local-model error typing or
  translation helpers for resolution vs endpoint failures
- `src/dynamic_agent_runner/__init__.py` — exports for any caller-visible local
  helper/config surface
- `tests/test_local_models.py` — new focused unit coverage for local-model
  config and resolution logic
- `tests/test_openai_client.py` — provider-seam and adapter-behavior coverage
- `tests/test_executor.py` — `local_only` routing and adapter-selection coverage
- `pyproject.toml` and `poetry.lock` — only if the model-resolution slice adds a
  runtime dependency on `huggingface_hub`

## Architecture and Data Flow

### First-slice endpoint-backed local chat

1. The caller provides runtime-owned local endpoint inputs such as base URL,
   optional API key, model aliases, and optional expected model identity.
2. A new local-model helper translates those inputs into repository-owned
   provider config plus `OpenAIClientAdapter` /
   `AsyncOpenAIClientAdapter` instances.
3. The helper defaults the adapter to `is_local=True` and advertises the caller's
   model aliases through the existing adapter metadata seam.
4. `executor.py` continues to select the adapter through `_select_model_and_adapter`
   and `_matching_model_adapters(...)` without a new local-provider branch.
5. Requests and responses continue to flow through `build_openai_request(...)`,
   `create_openai_response(...)`, and `normalize_openai_response(...)`.

### Later model-resolution extension

1. The caller provides an explicit local path, cache-root hint, or explicit
   Hugging Face reference.
2. The local-model helper resolves the effective model identity using the
   approved precedence order.
3. If the asset cannot be resolved, the helper raises a model-resolution error
   before execution.
4. If the endpoint is reachable but does not match the intended model identity,
   the runtime reports a model-mismatch failure rather than silently rerouting.

## Domain and Integration Boundaries

- Bounded context or owner: runtime adapter and local-model configuration inside
  `dynamic-agent-runner`
- Context relationship:
  - customer-supplier with the OpenAI-compatible provider seam already owned by
    this repository
  - separate-ways boundary for server installation and lifecycle owned by the
    caller or deployer
- Model translation:
  - repository-owned translation from local-model config into provider config and
    adapter metadata
  - repository-owned normalization from provider responses into `ModelResponse`
- Tactical pattern fit: thin config/helper layer over existing adapter and
  transport seams, with separate preflight resolution helpers for later slices
- Domain assumptions:
  - caller or deployer can provision the endpoint for the first slice
  - graph mutation stays in its own feature spec
  - local embedding support is a later slice, not a first-slice requirement

## Contracts

### Caller-facing local endpoint helper contract

- Input:
  - endpoint base URL
  - optional API key
  - one or more model aliases
  - optional provider name
  - optional expected model identity for mismatch reporting
- Output:
  - configured `OpenAIClientAdapter` or `AsyncOpenAIClientAdapter`
  - advertised `models`
  - `is_local=True` by default
- Errors:
  - invalid configuration
  - endpoint transport errors translated through repository-owned error handling
- Compatibility:
  - additive helper surface only; the existing adapter classes remain the
    canonical executor-facing boundary

### Later model-reference contract

- Input:
  - explicit local file path, explicit cache root, or explicit Hugging Face
    reference
- Output:
  - resolved local model identity and path metadata for runtime use
- Errors:
  - model-resolution failure
  - offline-policy block
  - model-identity mismatch
- Compatibility:
  - must extend the first-slice helper surface without changing executor
    routing semantics

## Verification Strategy

- FR-1 / FR-2 / FR-3 / FR-6 first slice:
  - `poetry run pytest tests/test_openai_client.py -q`
  - `poetry run pytest tests/test_executor.py -q`
- FR-4 response-normalization ownership:
  - `poetry run pytest tests/test_openai_client.py -q`
- FR-5 / FR-5b / FR-5c later resolution slice:
  - `poetry run pytest tests/test_local_models.py -q`
- Public export coverage if caller-visible helpers are added:
  - `poetry run pytest tests/test_import.py -q`
- Focused repository formatting and linting for implementation slices:
  - `pre-commit run --files src/dynamic_agent_runner/local_models.py`
    `src/dynamic_agent_runner/openai_client.py`
    `src/dynamic_agent_runner/__init__.py`
    `src/dynamic_agent_runner/errors.py` `tests/test_local_models.py`
    `tests/test_openai_client.py` `tests/test_executor.py`
    `tests/test_import.py` `2>&1`

Initial recorded evidence:

- T1.1 RED evidence in commit `a5798cc`:
  - Command: `poetry run pytest tests/test_openai_client.py -q 2>&1`
  - Observed outcome: `3 failed, 24 passed`
  - Expected RED reason: `ModuleNotFoundError: No module named
    'dynamic_agent_runner.local_models'`
- T1.2 RED evidence in commit `b79f124`:
  - Command: `poetry run pytest tests/test_executor.py -q 2>&1`
  - Observed outcome: `1 failed, 49 passed`
  - Expected RED reason: `ModuleNotFoundError: No module named
    'dynamic_agent_runner.local_models'`
- T1.3 GREEN evidence after commit `6d269ad`:
  - Command: `poetry run pytest tests/test_openai_client.py -q 2>&1`
  - Observed outcome: `27 passed in 0.17s`
  - Command: `poetry run pytest tests/test_executor.py -q 2>&1`
  - Observed outcome: `50 passed in 0.41s`
- T1.4 GREEN evidence after commit `ee0bf33`:
  - Command: `poetry run pytest tests/test_openai_client.py -q 2>&1`
  - Observed outcome: `29 passed in 0.15s`
  - Command: `poetry run pytest tests/test_executor.py -q 2>&1`
  - Observed outcome: `50 passed in 0.38s`
- T1.5 GREEN evidence after commit `dd37c62`:
  - Command: `poetry run pytest tests/test_import.py -q 2>&1`
  - Observed outcome: `1 passed in 0.19s`
  - Command: `poetry run pytest tests/test_openai_client.py`
    `tests/test_executor.py tests/test_import.py -q 2>&1`
  - Observed outcome: `80 passed in 0.47s`
  - Command: `poetry run pre-commit run --files
    src/dynamic_agent_runner/local_models.py
    src/dynamic_agent_runner/openai_client.py
    src/dynamic_agent_runner/__init__.py tests/test_openai_client.py
    tests/test_executor.py tests/test_import.py 2>&1`
  - Observed outcome: Ruff Check passed; Ruff Format passed

## Risks and Mitigations

- Risk: the feature scope expands the first slice into server ownership or graph
  mutation follow-up.
  - Mitigation: keep the first slice limited to endpoint-backed local chat and
    defer later work into separate checkpoints.
- Risk: local-model behavior leaks into executor-specific branches.
  - Mitigation: keep all local behavior behind adapter metadata and helper
    construction, then validate existing routing with executor tests.
- Risk: model-resolution and endpoint failures become indistinguishable.
  - Mitigation: add explicit local-model failure translation in the later
    resolution slice.
- Risk: dependency churn lands before the endpoint-backed slice proves value.
  - Mitigation: gate `huggingface_hub` dependency changes behind the later
    model-resolution slice.

## Rejected Alternatives

- Alternative: add a separate llama-specific executor path.
  - Rejected because existing adapter selection already provides the local
    routing boundary.
- Alternative: launch and supervise `llama_cpp.server` from the runtime library.
  - Rejected because the approved spec assigns server ownership to the caller or
    deployer.
- Alternative: start with in-process `llama_cpp.Llama` integration first.
  - Rejected because the approved first slice prefers the endpoint-backed path
    and the provider seam already exists.
- Alternative: combine embedding delivery with the first chat slice.
  - Rejected because the approved spec explicitly allows embedding work to land
    later.

## Plan Approval

- Status: active for Slice 2 follow-up after the completed Slice 1 checkpoint
- Notes: created by explicit user direction after the authoritative spec was
  approved and committed; the user later directed `execute T1.1 and commit`,
  producing RED commit `a5798cc`, and later directed T1.2 execution, producing
  RED commit `b79f124`. The user later directed T1.3 execution, producing
  implementation commit `6d269ad`, and later directed T1.4 execution,
  producing implementation commit `ee0bf33`. The user later directed T1.5
  execution, producing implementation commit `dd37c62`. Slice 1 is now complete
  through its export and focused-validation checkpoint, and broader follow-up now
  moves to Slice 2 planning/execution.
