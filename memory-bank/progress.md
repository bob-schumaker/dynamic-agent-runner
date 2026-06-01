# Progress

## Working

- `OA9` implementation and spec work is complete in `c181328`
  (`feat(registry): add tool-from-function helper`).
- OA9 added an optional `tool_from_function(...)` helper to the repository-owned
  registry layer, exposed it from the package root, and covered both explicit
  metadata plus inference fallback behavior for callable-derived tool
  definitions.
- Focused OA9 validation passed with:
  `poetry run pytest tests/test_registry.py tests/test_import.py -q 2>&1`
  (`32 passed`) and scoped `poetry run pre-commit run --files ...` on the OA9
  code/spec/doc files.
- The next active follow-up slice is `OA8`.

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
  - OA10 sandbox/workspace runtime metadata (`540f56a`)
  - OA9 optional `tool_from_function(...)` helper (`c181328`)

## In Flight

- The active ordered backlog is: `OA8`, then `OA11`.

## Remaining

- Start the next scoped implementation from `OA8` in the governing SDD docs.
- Keep extending the runner through package-owned interfaces rather than broad
  framework expansion.
- Continue using fake-client/fake-tool tests for unit coverage.
- Refresh the memory bank after each meaningful implementation milestone.

## Risks or Follow-ups

- More advanced runtime behavior remains deferred until explicitly selected:
  approval/resume engines, sessions, broader MCP integration, sandbox/workspace
  runtime execution, and iterative agent-loop semantics.
- `parallel_join`, `parallel_fanout`, and broader multi-agent execution remain
  unsupported runtime behavior.
- RAG/GraphRAG, portable tool taxonomy, handoffs, and agent-as-tool support are
  currently metadata/validation surfaces, not full runtime execution engines.
- Local llama.cpp and graph-mutation work remains feature-spec-only, with no
  active runtime implementation in the codebase.
