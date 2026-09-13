# Model Generation Resource Budgets Validation

## S5 — Darwin MPS no-model worker fixture

Date: 2026-09-13

The locally elevated arm64 macOS environment reported PyTorch MPS built and
available. The Darwin-only no-model fixture completed the fixed worker
lifecycle using the MPS allocator envelope before child resolution, followed by
pack, authorization, generation, and reap. Focused verification passed:
`43 passed in 6.25s` for `tests/test_generation_worker_controllers.py` and
`tests/test_local_model_runners.py`; Ruff and `git diff --check` also passed.

This is lifecycle evidence only. It does not replace T5.4/T4.6, which still
require an explicitly authorized locally prepared MPS model and redacted
aggregate result evidence.

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

## T4.7 — Automated validation

Date: 2026-09-12

- `poetry run pytest -q`: `2461 passed, 1 skipped, 7 deselected in 54.78s`
- `poetry run ruff check src tests`: passed
- `git diff --check`: passed

Converter-host vectors use a verified v2 model-material lock, a
generation-budget execution descriptor, its exact validator, matching runner
binding, and a host policy. One provider-unavailability ordering vector retains
its legacy fixture solely to prove that capability revalidation fails before
model admission.

The generic packed converter adapter requires its bound canonical budget before
sealed payload packing and no longer reads request `max_tokens` or
`max_continuations` aliases. The retained single-image model-family conformance
fixture continues to accept its public OpenAI request limit independently of
the generic converter path.
