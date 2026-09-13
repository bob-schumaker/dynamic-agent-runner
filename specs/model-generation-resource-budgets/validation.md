# Model Generation Resource Budgets Validation

## T5.4 — Authorized Darwin MPS prepared-model evidence

Date: 2026-09-13

The user explicitly authorized a local arm64 macOS MPS run with the reviewed
prepared floorplan Transformers/PEFT model, S5 converter fixture, and explicit
MPS host policy. The bounded effective limits were: 512 generated tokens per
fragment and in total, zero continuations, 32,768 output bytes, 4,096 effective
context tokens, 120,000 runtime milliseconds, and 30,150,672,384 memory bytes.

The content-free receipt recorded the lifecycle
`bootstrap_ready -> packed_receipt -> authorized -> reaped`. One completed
fragment recorded 194 packed-context tokens, 78 generated tokens, and 417
aggregate output bytes. The normal result exposed no model content, sealed
input, paths, handles, token IDs, or tensors.

The run first rejected a 128-token context ceiling and a one-token,
zero-continuation allowance at their intended admission limits. After raising
only those bounded limits, the worker completed. During this gate T5.9 exposed
and repaired the selected-controller child transport proxy; its spawned-child
regression proves a `packed` response delayed beyond the default IPC wait
reaches the parent under the configured lifecycle deadline.

## T5.8 — Sealed production floorplan package material

Date: 2026-09-13

The floorplan package now carries a v2 `model-materials.json` lock containing
the exact reviewed base and adapter artifact records, and a digest-bound
`execution-descriptor.json` with the canonical seven-field generation budget.
The package declares exact generic Transformers runner and converter
capabilities. DAR registers the matching descriptor validator and model-runner
provider by exact ABI, without a model-family-specific execution path.

Focused package, generic runner, and host composition verification passed:
`82 passed`. The missing-material regression proves a package with the
canonical converter capability binding is rejected before converter asset
validation. The legacy provider-unavailability ordering vector remains valid
because it deliberately does not declare that canonical converter binding.

## T5.11 — Floorplan workspace ingress configuration

Date: 2026-09-13

The dedicated reviewed floorplan host configuration now accepts the same
caller-approved workspace root and byte ceiling as the generic local-host
configuration. A focused regression first failed because the floorplan
configuration rejected `workspace_input_root`; it now registers the sealed
floorplan package and ingresses its declared `source_image` PNG through the
public host API. Focused verification passed: `1 passed`; Ruff and
`git diff --check` also passed.

## T5.12 — Co-located JSON response contract

Date: 2026-09-13

The generic worker asset bundle now carries the validated `json_object` mode
from the parent request to the co-located Transformers runner. The completed
parent response is validated as a JSON object, while other formats remain
rejected. The focused child-runtime regression first failed because the asset
bundle accepted no JSON contract; it now proves that the child receives
`json_mode=True`. Focused generic adapter, asset, and factory verification
passed: `85 passed`.

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

The DAR-owned MPS host-policy constructor verifies an explicit caller ceiling
against the reviewed MPS working-set capacity and supplies an atomic local
reservation provider. Focused controller and budget coverage passed: `44 passed
in 6.23s`.

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
