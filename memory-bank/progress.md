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
- Async-session support is currently metadata-only and documented as host-managed
  continuity for first-customer use cases.

## Latest Documentation Milestone

- Commit `a973ae8` (`docs(specs): add future feature specs`) added or refreshed:
  - `specs/README.md`
  - `specs/approval-interruption-resume/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/mcp-runtime-integration/spec.md`
  - `specs/live-guardrail-execution/spec.md`
  - `specs/skill-source-resolution/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/power-marimo-host-automation/spec.md`
  - primary roadmap/status consistency in `specs/dynamic-agent-runner/`
- The new future-feature specs capture known requirements, non-goals, design
  constraints, validation checklists, and `NEEDS CLARIFICATION` items. They do
  not authorize implementation by themselves.

## Remaining

- Optional llama.cpp Slice 3: separate local embedding configuration, if
  explicitly scheduled.
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
