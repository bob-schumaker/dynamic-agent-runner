# Tool-Input Guardrail V2 Validation Record

Status: implementation-ready; no V2 validation has run

## Required Evidence

- RED proof that tool-input declarations are not yet executed through the
  coordinator.
- GREEN proof that pass preserves direct and model-loop behavior.
- GREEN proof that abort and missing-adapter paths fail closed before approval,
  tool lifecycle hooks, retry, registry invocation, handler execution,
  state-result writes, and node output; existing node/workflow hooks remain.
- Redacted trace assertions: each selected declaration emits started followed
  by exactly passed, aborted, or errored; error paths then emit `workflow_error`.
- Error observations contain only declaration id, phase, node/tool ids, optional
  call id, and reason category—never subject, arguments, or details.
- Ordered multi-declaration, result-id/phase mismatch, and handler-error tests.
- Missing, empty, and whitespace-only ids; unsupported behavior-policy; and
  malformed guarded-input tests proving manifest validation or invocation fails
  before any guardrail, approval, tool lifecycle hook, retry, or handler runs;
  model-loop calls retain their existing pre-validation call observation.
- Subject assertions proving handlers receive only copied validated tool-input
  fields, never a raw handler, registry, provider callback, or interpreter;
  nested mutation cannot alter approval or handler arguments.

## Required Commands

```bash
poetry run pytest tests/test_guardrails.py tests/test_executor.py \
  tests/test_tracing.py tests/test_validation.py tests/test_capabilities.py \
  tests/test_import.py -q
poetry run ruff check src tests
poetry run pytest -q
poetry build
make -C docs html
```
