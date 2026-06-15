# Sandbox and Workspace Runtime Specification

## Metadata

- Feature slug: `sandbox-workspace-runtime`
- Mode: `light`
- Artifact type: future feature specification
- Status: approval-policy boundary implemented through approval-interruption v1;
  write/shell runtime remains deferred
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related runtime surfaces:
  - `runtime.execution_policy.sandbox_runtime`
  - opt-in read-only `local_workspace` built-in tool pack
  - tool policy metadata: `tool_type`, `side_effect`, `approval_required`,
    `sandbox`
  - approval interruption/resume future feature

## Objective

Define a future sandbox/workspace runtime that can safely expose write, patch,
shell, code-execution, and mounted-workspace capabilities to workflows under
explicit path grants, resource limits, approval policy, and observable runtime
boundaries.

## Existing Baseline

The current runtime preserves sandbox/workspace metadata and provides an opt-in
read-only local workspace pack. It intentionally does not provide write tools,
shell tools, apply-patch tools, package installation, workspace persistence, or
sandbox enforcement.

## Scope

This feature covers:

1. workspace manifests and path grants
2. write-capable file tools
3. patch tools
4. command/shell execution tools
5. resource limits and timeout policy
6. workspace persistence policy
7. approval-aware execution for mutating actions
8. trace and audit records for sandboxed actions

## Council Roadmap Note

The council review recommends pairing this feature with
`approval-interruption-resume` before broad MCP, loop, or interpreter execution.
The first useful slice should not attempt a full sandbox platform. It should
start with explicit path grants, one or two mutating workspace tools, approval
interruption before side effects, and a redacted changed-path summary.

## V1 Paired Slice Boundary

The first paired implementation slice does not add write, patch, delete, shell,
package-install, or mounted-workspace tools. It contributes the approval policy
side of sandbox safety by proving that approval-required direct tool actions
pause before any side effect.

This keeps the first slice small enough to validate without introducing a host
sandbox backend. Later sandbox slices can add explicit workspace grants and
mutating tools behind the approval boundary created by
`approval-interruption-resume`.

Implemented from this paired slice:

- direct approval-required tool steps pause before invocation
- no registered handler side effect occurs before approval
- approval pause traces mark requested arguments as sensitive
- capability status can report the live approval boundary

Still deferred:

- write, patch, delete, shell, package-install, and mounted-workspace built-ins
- explicit writable workspace grants and path authorization
- sandbox adapters and resource enforcement
- changed-path audit records for real workspace mutations

## Functional Requirements

### FR-1: Require explicit workspace grants

The runtime must not expose writable workspace capabilities without explicit
caller or deployment configuration.

Acceptance criteria:

- Given no workspace manifest or runtime grant, write and shell tools are
  unavailable even if a workflow references them.
- Given a workspace root is granted read-only, write, patch, and delete actions
  fail closed.
- Given a workspace root is granted writable access, write actions are still
  restricted to paths inside the granted root.
- Given a path includes symlinks, traversal, case-variant aliases, or relative
  components, validation resolves the effective path before authorization.

### FR-2: Separate read, write, patch, delete, and shell capabilities

The runtime must model each capability separately instead of enabling a broad
"workspace access" switch.

Acceptance criteria:

- `read_file`, `list_files`, `search_files`, and `inspect_path` remain separate
  from write and command tools.
- Write tools such as `write_file`, `create_directory`, and `delete_path` require
  explicit capability grants.
- Patch tools such as `apply_patch` require explicit patch capability and path
  grants.
- Shell tools require explicit command capability and must not inherit file-write
  capability implicitly.

### FR-3: Apply approval policy to mutating or risky actions

Mutating workspace actions must integrate with approval policy.

Acceptance criteria:

- Write, delete, patch, package-install, network, and shell actions default to
  approval-required unless an explicit trusted policy disables approval.
- Approval records include command text, normalized working directory, requested
  path changes, declared side effects, and redacted environment details.
- Rejected approval prevents the action from running.
- Approved action uses the exact approved command or file operation.

### FR-4: Enforce resource limits

Sandboxed actions must be bounded.

Acceptance criteria:

- Commands support timeout, output-size, working-directory, environment, and
  optional CPU/memory constraints when the selected backend supports them.
- File operations enforce max file size, max write size, max patch size, and max
  number of changed files.
- Tool results separate model-facing output, raw output, log preview, event
  payload, and sensitive trace fields.
- Exceeding limits fails clearly and records a trace event.

### FR-5: Support backend-specific sandbox adapters

The runtime should own a narrow sandbox adapter interface rather than hard-code
one process-isolation technology.

Acceptance criteria:

- A sandbox adapter can be in-process file operations only, subprocess-backed,
  container-backed, VM-backed, or host-provided.
- The adapter reports supported capabilities and limits before tools are exposed.
- Unsupported requested capabilities fail during preparation.
- Backend-specific implementation details do not leak into portable workflow
  package fields.

### FR-6: Track workspace state and audit records

The runtime must make mutations inspectable.

Acceptance criteria:

- Each mutating action records changed paths, action id, tool id, node id, run id,
  approval id when applicable, and before/after metadata when available.
- Workspace persistence policy distinguishes ephemeral, in-memory, local-folder,
  and external-checkpoint workspaces when implemented.
- The runtime can report a summary of changed paths at workflow completion.
- Sensitive file content is not included in traces unless explicitly allowed.

## Non-Goals

- No default write or shell capability.
- No built-in container runtime requirement in v1.
- No guarantee that every backend can enforce every resource limit.
- No portable workflow fields for machine-specific absolute paths, credentials,
  package managers, or shell profiles.
- No bypass of approval policy through interpreter middleware or MCP tools.

## Design Constraints

- Keep sandbox runtime separate from the current read-only `local_workspace`
  built-in pack.
- Keep generated workflow packages portable and environment-agnostic.
- Fail closed when grants, paths, capabilities, or backend support are ambiguous.
- Treat command execution as a high-risk capability with explicit approval and
  redaction rules.

## NEEDS CLARIFICATION

- What sandbox adapter backends should v1 support?
- Should write tools be built-in packs, caller-registered tools, or both?
- What path-grant format should callers use?
- What default approval policy applies to write, patch, delete, shell, network,
  and package-install actions?
- Which command forms are allowed: argv-only, shell strings, allowlisted
  commands, or arbitrary commands with approval?
- How should environment variables and secrets be passed or blocked?
- Should workspace persistence be implemented in v1 or left metadata-only?
- What changed-file summary format should be public API versus trace-only?
- How should sandbox tools interact with approval interruption/resume?
- Should apply-patch semantics use a repository-owned patch parser or a delegated
  backend command?

## Validation Checklist

- [ ] Write/shell tools are unavailable without explicit grants.
- [ ] Path traversal and symlink escapes fail closed.
- [ ] Read-only grants reject write, patch, and delete operations.
- [ ] Mutating actions produce approval interruptions by default.
- [ ] Resource limits are enforced or unsupported limits fail during preparation.
- [ ] Trace events include redacted audit records for mutating actions.
- [ ] Backend capability mismatch fails before execution.
