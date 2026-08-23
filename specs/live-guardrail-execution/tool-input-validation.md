# Tool-Input Guardrail V2 Validation Record

Status: implementation-ready; no V2 validation has run

## Required Evidence

- RED proof that tool-input declarations are not yet executed through the
  coordinator.
- GREEN proof that pass preserves direct and model-loop behavior.
- GREEN proof that abort and missing-adapter paths fail closed before approval,
  hooks, retry, registry invocation, handler execution, state-result writes,
  and node output.
- Redacted trace assertions for tool-input phase observations.
- Ordered multi-declaration, result-id/phase mismatch, and handler-error tests.
- Subject assertions proving handlers receive only copied validated tool-input
  fields, never a raw handler, registry, provider callback, or interpreter.

## Required Commands

```bash
poetry run pytest tests/test_guardrails.py tests/test_executor.py \
  tests/test_tracing.py tests/test_capabilities.py tests/test_import.py -q
poetry run ruff check src tests
poetry run pytest -q
poetry build
make -C docs html
```
