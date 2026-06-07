# Progress

## Working

- `dynamic-agent-runner` has a working Python package under
  `src/dynamic_agent_runner/`, tests under `tests/`, user-facing docs under
  `docs/`, and SDD/spec artifacts under `specs/`.
- The runtime supports package-directory workflow loading and execution,
  async-first APIs, sync compatibility wrappers, repository-owned tool registry
  and overrides, OpenAI-compatible provider/client facades, retry, output
  contracts, token budgeting, tracing, lifecycle hooks, runtime behavior
  overrides, prompt preparation, and package-owned validation.
- Provider-wrapper support is implemented through Slices 1-6 and exposes
  package-level provider configuration for OpenAI-compatible endpoints.
- llama.cpp local-model support is implemented through Slice 2: endpoint helper
  construction, provider-seam wiring, package exports, model-resolution
  precedence, Hugging Face download wiring, local endpoint failure taxonomy, and
  authoritative model-identity mismatch reporting.
- Internal graph mutation has a complete first checkpoint: typed mutation
  datamodels, context-pruning mutation, fail-closed attachment validation,
  prepared-input integration, and mutation diagnostics.
- Public Hugging Face model discovery is implemented: callers can use
  `search_hugging_face_models(...)` and receive
  `HuggingFaceModelSearchResult` values with package-owned
  `HuggingFaceModelSearchError` failure translation.
- Model adapter coverage policy is implemented: callers can choose
  `model_adapter_coverage="strict"` for authoritative supplied adapters or rely
  on default augmented behavior for eligible default OpenAI coverage.
- Async-session support is currently metadata-only and documented as host-managed
  continuity for first-customer use cases.

## Latest Documentation and Spec Milestones

- Commit `9354d24` aligned `README.md` and authored Sphinx docs with the current
  repo setup, local-model helper boundary, Hugging Face discovery coverage, and
  package dependency direction. Validation for that docs slice included
  `make -C docs html` and targeted pre-commit on the tracked docs files.
- Commit `2429727` documented the implemented model adapter coverage policy in
  README, Python API docs, specs, and memory. Commit `cb52cd0` then clarified
  the repository-local dynamic-agent-runner skill with default OpenAI behavior,
  strict vs augmented adapter coverage, and local llama.cpp adapter usage.
- Commit `8216ca7` added the authoritative Hugging Face model-search spec.
- Commits `4c83c2b`, `b343a9c`, `af8b2a0`, and `191f722` made that spec
  actionable, added RED contract tests, implemented the public discovery API,
  and documented it.
- Commit `3f5b51f` synchronized the primary spec, feature-spec statuses,
  `specs/README.md`, and the completion matrix after the Hugging Face feature
  landed.
- Commit `2425a4e` added `specs/hugging-face-support-layer/spec.md` and indexed
  it in `specs/README.md` as a future internal refactor for shared
  `huggingface_hub` import/call/error mechanics.
- Future-feature specs still capture known requirements, non-goals, design
  constraints, validation checklists, and clarification items. They do not
  authorize implementation by themselves.
- The model adapter coverage policy landed with public API/context wiring,
  strict supplied-adapter failure behavior, augmented default OpenAI coverage,
  local-only routing removal, focused tests, client-facing docs, and
  repository-local skill guidance for default OpenAI and local llama.cpp adapter
  usage.

## Remaining

- Optional llama.cpp Slice 3: separate local embedding configuration, if
  explicitly scheduled.
- Future richer Hugging Face Hub behavior beyond read-only model discovery; this
  requires a separate feature spec.
- Ongoing docs hygiene: keep `README.md` and authored Sphinx files under
  `docs/files/` aligned with the current package surface and regenerate
  `docs/source/*.rst` through the docs Makefile instead of hand-editing generated
  pages.
- Internal Hugging Face support-layer refactor: centralize lazy Hub import,
  read-only SDK calls, and domain-specific error translation while preserving
  separate discovery and local-model download contracts.
- Live approval interruption/resume engine and serialized resume state.
- Writable sandbox/workspace runtime, write/patch/shell tools, and command
  approval policy.
- Live MCP source discovery, lifecycle management, registry injection, and tool
  invocation.
- Live guardrail adapter execution and abort/reject behavior.
- Trusted `SKILL.md` body loading, source precedence, and prompt injection.
- Iterative model/tool loop runtime and stop policy.
- Power-Marimo live host automation, Marimo-session tools, domain adapters, and
  optional PyQt-widget automation.

## Risks or Follow-ups

- Do not treat future-feature specs as implementation approval; create a scoped
  plan/task slice first.
- Keep generated workflow packages portable: no machine-specific local paths,
  credentials, server lifecycle details, notebook handles, or GUI handles in
  base package artifacts.
- Keep high-risk capabilities fail-closed: write, shell, MCP, approval, guardrail,
  notebook automation, and arbitrary skill-source loading need explicit policy
  before live execution.
