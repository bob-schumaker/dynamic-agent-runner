# Workflow Model Support Matrix Discovery

## Outcome

Define one capability-gated test matrix for Fastmail-triage, embedding/index,
sealed multimodal generation, structured-output tool loops, stateful context,
and injected tool-pack composition. The matrix must distinguish genuine support
from combinations that are unavailable, deferred, or inappropriate to run.

## Users and Problem

- Users: DAR maintainers and a human operator approving live workflow probes.
- Problem: the controlled S1--S6 model-interface matrix proves adapter tool
  semantics, but it does not exercise workflow-owned converter/generation,
  structured-output, session/context, or tool-pack composition contracts.
- Success example: a maintainer can see which workflow/profile cells have
  automated evidence, which are eligible for an authorized live probe, and why
  every remaining cell is not runnable.

## Existing Patterns and Boundaries

- `model-interface-parity` provides harmless, fake-backed tool tests and an
  opt-in live positive runner; it intentionally excludes Fastmail, MCP, and
  external acceptance.
- `fastmail-inbox-triage` owns the sealed workflow and its read-only acceptance.
  Its current package is locked to its Qwen material closure; it cannot be
  silently reused as evidence for another generation provider.
- `workflow-embedding-index-artifacts` owns sealed embedding/index artifacts.
  DAR admits a generic ABI/provider implementation but workflow packages lock
  their own model material closure.
- The floorplan SVG fixture exercises sealed multimodal ingress, conversion,
  bounded generation, and workflow-owned output validation. Its successful MPS
  probe is package-specific evidence, not a cross-adapter result.
- Sessions/context and tool packs already have fake test seams. Their support
  profiles must use injected deterministic adapters and clients; they must not
  promote external retrieval, web, workspace, or subagent execution to live
  matrix work.
- Model/interface support is capability-dependent. A missing generation tool
  path, embedding ABI, material binding, or eligible host is a classified cell,
  not a failed test.

## Commands and Testing

- Focused automated tests: `poetry run pytest <selected test files> -q`
- Full automated verification: `poetry run pytest -q`
- Lint: `poetry run ruff check src tests`
- Manual live probes remain operator-authorized and must retain redacted
  receipts only.

## Component Disposition

Single coherent unit. The capability classifier, fixture selection, receipt
format, and status matrix must agree; separating Fastmail and embedding into
unrelated artifacts would duplicate their common support-state contract.

## Open Questions

- No product ambiguity blocks planning. Exact initial profiles and fixture
  package IDs are implementation-time discovery tasks because availability is
  host- and material-dependent.
- The MLX generic embedding backend is implemented, but its real workflow row
  remains excluded until MLE6 seals and validates one package/material closure.
  Sandboxed write/shell execution and runner-owned RAG remain excluded until
  their owning contracts are implemented and admitted.
