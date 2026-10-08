<!-- markdownlint-disable MD013 -->
# DAR External Adapter Protocol Validation

Status: implementation validated

## Focused tests

```text
poetry run pytest tests/test_external_adapter_protocol.py tests/test_external_adapter_registry.py tests/test_executor.py tests/test_openai_client.py tests/test_cli.py tests/test_external_adapter_cli.py -q
346 passed
```

The focused tests cover public exports, descriptor and digest validation,
immutable limits, text-only request admission, structured-output validation,
redacted responses, tool-handler isolation, bounded sync/async dispatch,
private single-use dispatch tokens, raw BYOM normalization, exact model
selection, registry persistence/reload/tamper handling, and adapter CLI
dispatch.

## Full root validation

```text
poetry run pytest -q
2736 passed, 1 skipped, 7 deselected

poetry run ruff check src tests
All checks passed
```

## Chrome package validation

```text
cd plugins/dar-chrome-external-adapter
poetry check
poetry run ruff check dar_chrome_external_adapter tests
All checks passed
PYTHONPATH=.:../../src poetry run pytest -q
4 passed
poetry build
poetry run python scripts/verify_built_artifact.py --dist dist
dist/dar_chrome_external_adapter-0.1.0-py3-none-any.whl
```

The package-local fake bridge tests cover text-only descriptor projection,
unavailable default health, trusted extension/origin checks, request-context
binding, replay protection, and install→reload→façade execution through a
fake bridge. The deterministic artifact check confirms the manifest and
factory package are present in the wheel.

## Lifecycle smoke

The receiver CLI was exercised against the built wheel with a temporary DAR
state root:

```text
dynamic-agent-runner adapter install --state-root <temporary-root> <plugin-wheel>
dynamic-agent-runner adapter list --state-root <temporary-root>
dynamic-agent-runner adapter remove dar.chrome.external --state-root <temporary-root>
```

Install, list, remove, and the final empty list all returned JSON success
receipts. Reload revalidated the wheel digest before factory import.

## Scope audit

- Ordinary DAR execution does not scan for Chrome or import the optional
  plugin.
- Protocol v1 remains text-only and final-response-only.
- Streaming, multimodal, persistent-session, native-callback, AFM, Ollama,
  marketplace, and per-node-binding migrations remain deferred.
- Unit tests use fake adapters and bridges only; no live Chrome or remote model
  call is part of this validation.
