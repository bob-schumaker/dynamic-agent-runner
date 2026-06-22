# Host Workflow Integration Slice H2 Tasks

## Status

Implemented.

## Tasks

1. [x] RED: Add package-free preflight tests for an inline runtime manifest mapping.
   - Verification: the report is valid, has the expected `package_id`, and
     includes the same core runtime/model/tool capability items as package
     inspection.

2. [x] RED: Add package-free preflight tests for an inline runtime manifest YAML
   string.
   - Verification: no temporary package directory is created or required, and
     the returned object is a `CapabilityStatusReport`.

3. [x] RED: Add loaded-workflow preflight tests.
   - Verification: passing a `LoadedAgentWorkflow` inspects that object without
     reloading artifacts and preserves caller-supplied registry/model/session
     collaborators.

4. [x] RED: Add invalid inline manifest tests for strict and non-strict behavior.
   - Verification: non-strict returns `valid=False` with `package.validation`;
     strict raises the package-owned validation/load error.

5. [x] RED: Add host tool metadata capability tests.
   - Verification: when a registry built from `HostToolBinding` satisfies a
     manifest tool, the relevant tool capability details include
     `host_canonical_id`, `host_model_id`, and `host_aliases` when present.

6. [x] GREEN: Refactor capability inspection around a loaded workflow helper.
   - Verification: existing package-directory capability tests still pass.

7. [x] GREEN: Add the public inline/loaded workflow preflight helper and export
   it.
   - Verification: imports from `dynamic_agent_runner` expose the helper and
     `tests/test_import.py` passes.

8. [x] GREEN: Extend host-bound tool capability details without changing item ids
   or states.
   - Verification: existing capability summary tests remain stable except for
     the explicitly added host id fields.

9. [x] GREEN: Update public lifecycle documentation.
   - Verification: README and `docs/files/python-api.rst` distinguish direct
     execution, reusable `WorkflowExecutionContext`, and `AgentSession`, and do
     not imply new lifecycle semantics.

10. [x] Final validation.
    - Verification: run the focused commands in [`validation.md`](validation.md)
      and then the final package lint/test commands listed there.

## Stop Conditions

- Stop and rescope if inline preflight requires filesystem package artifacts for
  skill-bundle loading. H2 may report package-local skill source resolution as
  metadata-only for inline workflows unless a package root is supplied.
- Stop and rescope if host metadata requires changing `ToolDefinition`'s public
  schema rather than reading existing `definition.raw` fields.
