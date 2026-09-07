# Local Model Runner Interface Validation

## Readiness Review — 2026-09-07

Council review used the AI triad (Karpathy, Sutskever, Ada) in parallel
advisory passes. They agreed the earlier task set was not ready because the
loader profile, closure invariants, offline guarantees, decoding, media limits,
catalog precedence, and manual evidence were descriptive rather than testable.

Ponytail review accepted one closed built-in profile as the smallest useful
slice. It rejected adding a plugin ABI, generic scheduler, dynamic model
registry, or arbitrary framework support to solve this Qwen use case.

The revised specification and task set resolve those findings with one fixed
`transformers-peft-single-image-v1` profile, explicit rejection boundaries,
and RED/GREEN tasks. The task set is ready for implementation; no code or
runtime validation is claimed by this review.

## Readiness Disposition — 2026-09-07

The current MPS remediation is **implementation-ready for T5 under its stated
gates**. The bounded implementation seam is
`workflow_host/transformers_peft_model.py::_load_default_backend`; T5.1 and
T5.2 define test-first observable behavior, T5.3 is the only implementation
step, T5.4 is the full regression gate, and T5.5 is the already-authorized
real-model gate. Floorplan JSON parsing remains a workflow-local parser check,
not a DAR runner responsibility.

### Council and Ponytail Refresh

The AI triad reviewed the current MPS slice in independent first passes and a
challenge round. Its material findings were resolved in the artifact set:

- MPS now has an observable load-base, move-to-MPS, attach-PEFT order.
- Fake tests claim only that observable call/input behavior; T5.5 remains the
  real-framework proof that offloaded dispatch is avoided.
- MPS move and adapter-attachment failures clear sealed input, use DAR's
  redacted error path, and do not retry through CPU/disk offload.
- The floorplan JSON parser is explicitly workflow-local.

The Council suggestion to pass an additional PEFT placement argument was not
adopted. The pinned PEFT API exposes no placement default; its offload handling
is conditional on the base model's existing device map. Omitting the base
`device_map` in the MPS branch is the smaller, testable contract.

Ponytail review found no complexity to remove: the slice adds no public device
setting, scheduler, allocator, plugin interface, or dependency. **Lean already.
Ship.**

### Plan Refresh Review

The Council re-reviewed `plan.md` after its T5 execution sequence was made
explicit. It found no material plan/spec/task mismatch: the sequence maps to
FR-5 and its acceptance criteria, maintains the sealed/offline boundaries, and
leaves actual framework behavior to the authorized real gate. Ponytail found
no plan complexity to remove. The plan is ready to execute under its stated
gates.

## Task Traceability

| Requirement | Tasks |
| --- | --- |
| Exact built-in selection and verified closure | T1, T3.1–T3.2 |
| Offline generic loading and normalized output | T2.1–T2.4 |
| Sealed input, limits, and cleanup | T2.2–T2.4 |
| Client-runner escape hatch without shadowing | T3.1–T3.2 |
| Full verification and real-model gate | T4.1–T4.2, T5.4–T5.5 |
| Generic MPS placement without a scheduler | T5.1–T5.5 |

## Implementation Evidence — 2026-09-07

- T1 RED: `tests/test_local_model_preparation.py` initially failed with the
  missing `TRANSFORMERS_PEFT_SINGLE_IMAGE_V1` import. T1 GREEN:
  `poetry run pytest tests/test_local_model_preparation.py -q` — `10 passed`.
- T2 RED: importing the new runner test initially failed because
  `dynamic_agent_runner.workflow_host.transformers_peft_model` did not exist.
  T2 GREEN: fake-only loader, media, deterministic decoding, empty-output, and
  cleanup coverage in `tests/test_transformers_peft_model.py` — `10 passed`.
- T3 coverage in `tests/test_local_model_runners.py` verifies the DAR-owned ID
  is reserved, the Qwen profile routes lazily to the built-in adapter, and a
  nonstandard client runner remains usable. The focused T1–T3 regression run:
  `poetry run pytest tests/test_transformers_peft_model.py
  tests/test_local_model_runners.py tests/test_dar_authoring_profiles.py
  tests/test_local_model_preparation.py tests/test_fastmail_triage_model.py -q`
  — `43 passed`.
- `poetry lock` regenerated the optional dependency closure; `poetry.lock` was
  not edited directly.
- T4.1: `poetry run pytest -q` — `1852 passed, 1 skipped, 7 deselected`;
  `poetry run ruff check src tests` — passed; `git diff --check` — passed.
- Manual-run preparation regression: `poetry run pytest
  tests/test_local_model_preparation.py -q` — `11 passed`; the added coverage
  proves the generic runner's verified groups materialize below one private
  root.
- Host configuration regression: `poetry run pytest
  tests/test_dar_authoring_host.py::test_configure_qwen25_vl_3b_floorplan_grpo_transformers_peft_host
  -q` — `1 passed`.

## Authorized Manual Run — 2026-09-07

The user authorized the real-model gate. The optional runtime was installed and
the pinned base/adapter closure was prepared in a private temporary root. The
sealed floorplan image run reached PEFT adapter loading, but produced no model
output: the MPS-capable host took the automatic placement path, which used
CPU/disk offload before PEFT applied the adapter. The adapter then rejected the
offloaded dispatch state.

This run recorded no prompt text, image bytes, artifact paths, vendor exception
text, or generated output. It is evidence for T5, not successful T4.2/T5.5
acceptance. The run also exposed two repaired preparation/runtime dependencies:
the generic runner now materializes its verified closure under one private root,
and the optional runtime includes the processor's required Torchvision package.

## T5 Completion — 2026-09-07

- T5 RED: `poetry run pytest tests/test_transformers_peft_model.py -q` —
  `5 failed, 9 passed`; each new test failed because the MPS-capability seam
  did not yet exist.
- T5 GREEN: the focused runner suite — `14 passed`; scoped Ruff check passed.
  It covers MPS/no-MPS loader arguments and order, wrapped-model input device,
  and sealed-input cleanup/redaction after MPS-move or adapter-attachment
  failure.
- T5.4 focused regression: `poetry run pytest
  tests/test_transformers_peft_model.py tests/test_local_model_preparation.py
  tests/test_local_model_runners.py tests/test_dar_authoring_host.py -q` —
  `46 passed`.
- T5.4 full regression: `poetry run pytest -q` — `1858 passed, 1 skipped, 7
  deselected`; `poetry run ruff check src tests` and `git diff --check` passed.
- T5.5: with the already-authorized pinned closure and sealed floorplan image,
  the MPS runner loaded and the workflow-local parser accepted a nonempty JSON
  object. An initial richer polygon request reached the 1,024-token ceiling and
  was correctly rejected as incomplete JSON; a compact, bounded room/bounding-
  box contract completed within that same runner limit. No prompt text, image
  bytes, paths, vendor exception text, or generated content is recorded.
