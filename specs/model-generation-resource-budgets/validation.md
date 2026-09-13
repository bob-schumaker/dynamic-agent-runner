# Model Generation Resource Budgets Validation

## T4.6 — Fixture-only Darwin pre-dispatch evidence

Date: 2026-09-12

The user explicitly authorized this fixture-only manual check. The host exposed
no reviewed Metal/MPS worker runtime and therefore rejected the CPU worker
before sealed-input ingress. The process exited normally with the redacted
outcome `pre_dispatch_memory_budget_unavailable`.

Effective limits recorded by the harness:

- `max_new_tokens_per_fragment`: 1
- `max_continuations`: 0
- `max_total_generated_tokens`: 1
- `max_total_output_bytes`: 4096
- `max_effective_context_tokens`: 128
- `max_runtime_milliseconds`: 120000
- `max_memory_bytes`: 68719476736

No prompt, sealed payload, model output, model/cache path, or worker exception
detail was recorded. A worker receipt is not applicable because admission was
rejected before worker launch.
