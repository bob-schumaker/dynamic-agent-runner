# Host Workflow Integration Slice H2 Validation

## Validation Goals

The implementation is complete when hosts can preflight generated workflows
without fake package directories, host-bound tool reports expose useful id
metadata, and public docs explain the supported lifecycle choices without adding
new semantics.

## Focused Checks

```bash
poetry run pytest tests/test_capabilities.py -q
poetry run pytest tests/test_host_integration.py -q
poetry run pytest tests/test_import.py -q
```

## Final Checks

```bash
poetry run ruff check src tests
poetry run pytest -q
```

## Manual Review Checklist

- Inline preflight accepts mappings and raw YAML strings.
- Loaded-workflow preflight accepts `LoadedAgentWorkflow`.
- Package-directory preflight remains unchanged.
- Strict invalid inline input raises the underlying package-owned error.
- Non-strict invalid inline input returns an invalid `CapabilityStatusReport`.
- Host-bound tool details expose canonical/model-facing ids and aliases only
  when those fields are available.
- No live model, network, GUI, or downstream host application calls are added to
  tests.
- No generated docs under `docs/source/` are edited by hand.
