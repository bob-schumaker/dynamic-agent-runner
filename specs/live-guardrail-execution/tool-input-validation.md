# Tool-Input Guardrail V2 Validation Record

Status: complete

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

## Observed Evidence

- RED: `poetry run pytest tests/test_validation.py tests/test_executor.py -q`
  produced five V2-boundary failures before implementation: omitted tool-input
  behavior was rejected, whitespace identifiers were accepted, and direct
  tool-input declarations neither executed nor failed closed.
- GREEN focused gate: `poetry run ruff check src tests` and
  `poetry run pytest tests/test_guardrails.py tests/test_executor.py
  tests/test_tracing.py tests/test_validation.py tests/test_capabilities.py
  tests/test_import.py -q` passed with `251 passed in 0.74s`.
- Full suite: `poetry run pytest -q` passed with `694 passed, 4 skipped in
  1.68s`.
- Package build: `poetry build` completed successfully.
- Documentation build: `poetry run make -C docs html` completed successfully.
  The bare `make -C docs html` command could not find the Poetry-managed
  `sphinx-build` executable, so the equivalent project-environment command was
  used.

The focused tests prove direct and model-loop pass/abort behavior, missing
adapters, handler failures, malformed results, id/phase mismatches, unsupported
policy, copied nested arguments, and redacted error traces. Output and
tool-output phases, reject-content, retries, timeouts, and external adapters
remain deferred.
