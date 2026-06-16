# RAG Orchestration Contract V1 Tasks

Status: prepared for implementation

## Slice 0 — Planning Checkpoint

- [x] T0.1 Resolve v1 metadata location, execution boundary, collaborator,
      retrieved-context, parsed-query, answer-state, evaluation, and
      capability/status decisions in `spec.md`.
- [x] T0.2 Add `plan.md`, `tasks.md`, and `validation.md` before
      implementation.
- [x] T0.3 Run planning-artifact validation.
  - Validation:
    `pre-commit run --files specs/rag-orchestration-contract/spec.md`
    `specs/rag-orchestration-contract/plan.md`
    `specs/rag-orchestration-contract/tasks.md`
    `specs/rag-orchestration-contract/validation.md specs/README.md`
  - Result: passed
- [ ] T0.4 Commit the planning checkpoint before code changes if requested.

## Slice 1 — Declarative RAG Metadata Validation

- [x] T1.1 [tests] Add RED validation tests for staged RAG metadata.
  - Spec: FR-1, FR-2, FR-6, FR-7, FR-11
  - Files/components: `tests/test_validation.py` or
    `tests/test_rag_orchestration.py`
  - Acceptance:
    - staged hybrid RAG metadata with retrievers, fusion, candidate budget,
      context assembly, permission, source readiness, cache, and degraded states
      is accepted
    - malformed stage shapes and unsupported enum values fail with
      field-specific messages
    - existing minimal `metadata.rag_pipeline` coverage remains valid
  - Validation:
    `poetry run pytest tests/test_validation.py -q`

- [x] T1.2 [implementation] Expand `metadata.rag_pipeline` validation without
      changing execution behavior.
  - Spec: FR-1, FR-2, FR-6, FR-7, FR-11
  - Files/components: `src/dynamic_agent_runner/validation.py`
  - Acceptance:
    - supported values are centralized as constants near existing RAG
      validation constants
    - list/mapping/boolean/integer checks reuse existing validation helpers
      where practical
    - unknown infrastructure dependencies are not introduced
  - Validation:
    `poetry run pytest tests/test_validation.py -q`

- [x] T1.3 [docs] Update authored artifact-package docs for the v1 metadata
      shape.
  - Spec: FR-1, FR-2
  - Files/components: `docs/files/artifact-package.rst`
  - Acceptance:
    - docs state the metadata-only boundary
    - docs show primitive-node RAG with declarative retriever metadata
  - Validation:
    `pre-commit run --files docs/files/artifact-package.rst`

## Slice 2 — RAG Collaborator Capability Status

- [x] T2.1 [tests] Add RED capability/status tests for RAG readiness.
  - Spec: FR-3, FR-10, FR-11
  - Files/components: `tests/test_capabilities.py`
  - Acceptance:
    - metadata-only RAG declarations produce a RAG metadata/status item
    - caller-supplied registry coverage for required retriever tool ids reports
      live
    - missing required retriever tool ids report missing collaborator
    - optional missing retrievers do not invalidate the package
    - stale/degraded declarative states appear in redaction-safe details
  - Validation:
    `poetry run pytest tests/test_capabilities.py -q`

- [x] T2.2 [implementation] Add RAG capability/status reporting without
      invoking retrieval.
  - Spec: FR-3, FR-10, FR-11
  - Files/components: `src/dynamic_agent_runner/capabilities.py`
  - Acceptance:
    - no live tools are invoked
    - existing tool-registry status behavior is reused
    - report details identify orchestration mode, retrieval mode, required
      retriever count, covered retriever count, missing retriever ids, and
      degraded states when present
  - Validation:
    `poetry run pytest tests/test_capabilities.py tests/test_validation.py -q`

## Slice 3 — Provenance and Context-Management Handoff Metadata

- [x] T3.1 [tests] Add RED tests for provenance-required and context-assembly
      declarations.
  - Spec: FR-4, FR-5, FR-8, FR-9
  - Files/components: `tests/test_validation.py`,
    `tests/test_capabilities.py`
  - Acceptance:
    - `provenance_required: true` requires declared evidence fields or a
      required provenance-producing retriever declaration
    - context assembly target values are validated
    - context token budgets must be positive integers when present
    - capability/status details include provenance/context readiness without raw
      retrieved content
    - tests prove RAG metadata declares handoff requirements but does not pack
      or inject retrieved context
  - Validation:
    `poetry run pytest tests/test_validation.py tests/test_capabilities.py -q`

- [x] T3.2 [implementation] Validate and report provenance/context-management
      handoff metadata.
  - Spec: FR-4, FR-5, FR-8, FR-9
  - Files/components: `src/dynamic_agent_runner/validation.py`,
    `src/dynamic_agent_runner/capabilities.py`
  - Acceptance:
    - implementation remains declarative and does not pack or inject retrieved
      context
    - details are redaction-safe and do not include raw evidence content
    - context-management ownership of retrieved-context lanes remains documented
  - Validation:
    `poetry run pytest tests/test_validation.py tests/test_capabilities.py -q`

## Slice 4 — Completion Evidence

- [ ] T4.1 [validation] Run focused affected tests.
  - Command:
    `poetry run pytest tests/test_validation.py tests/test_capabilities.py -q`

- [ ] T4.2 [validation] Run the full suite unless scoped narrower by explicit
      implementation notes.
  - Command: `poetry run pytest -q`

- [ ] T4.3 [validation] Run focused pre-commit over touched files.
  - Command:
    `pre-commit run --files src/dynamic_agent_runner/validation.py`
    `src/dynamic_agent_runner/capabilities.py tests/test_validation.py`
    `tests/test_capabilities.py docs/files/artifact-package.rst`
    `specs/rag-orchestration-contract/spec.md`
    `specs/rag-orchestration-contract/plan.md`
    `specs/rag-orchestration-contract/tasks.md`
    `specs/rag-orchestration-contract/validation.md specs/README.md`

- [ ] T4.4 [docs] Record completion evidence and update spec/memory status
      before the next focus area.

## Done Definition

- RAG remains an orchestration contract over primitive nodes.
- Expanded RAG metadata validates with clear errors.
- Capability/status distinguishes metadata-only, live covered retrievers,
  missing required collaborators, and degraded declarative states.
- No retrieval infrastructure dependencies or live retrieval calls are added.
- Existing RAG and non-RAG manifests remain compatible.
- Tests use fake registries/tools only.
