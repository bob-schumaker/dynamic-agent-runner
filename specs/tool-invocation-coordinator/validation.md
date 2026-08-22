# Tool Invocation Coordinator Validation Record

## Preparation Baseline

- Date: 2026-08-22
- Command:

  ```bash
  poetry run pytest \
    tests/test_executor.py \
    -k pauses_approval_required_model_tool_before_invocation -q
  ```

- Result: passed (`1 passed, 129 deselected in 0.17s`)
- Meaning: current model-loop approval pause prevents handler invocation. This
  is baseline evidence only; it does not prove coordinator extraction parity.

## Required Implementation Evidence

- RED evidence that approval-required malformed input fails before an
  interruption, while non-approval failure behavior remains unchanged.
- RED evidence that an unresolved approval has no handler, hook, retry, or
  tool-result/node-output/failure-policy state side effect, while the direct
  node-input snapshot remains and model-loop observation order is retained.
- RED evidence for the model-loop unknown, malformed, paused, and dispatched
  event sequences, plus the existing `direct_model_only` invocation outcome.
- GREEN evidence that registry preparation is non-invoking, preserves one
  resolved tool and copied argument mapping through dispatch, and remains
  separate from origin-specific exposure checks.
- GREEN evidence for each migrated origin, with the executor wrapping an
  `ApprovalInterruption` rather than the coordinator returning a workflow result
  and persisting retry/state/output behavior outside the coordinator.
- Focused:

  ```bash
  poetry run pytest tests/test_registry.py tests/test_executor.py \
    tests/test_hooks.py tests/test_tracing.py -q
  ```

- Full: `poetry run pytest -q`
- Lint: `poetry run ruff check src tests`
- Build: `poetry build`
- Documentation: `make -C docs html`

No implementation validation has been run yet.
