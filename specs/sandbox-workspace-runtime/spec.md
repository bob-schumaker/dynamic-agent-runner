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
- Evaluated supporting reference:
  - `https://github.com/MARKTECHPOST-AI-MEDIA-INC/AI-Agents-Projects-Tutorials`
    includes useful staged-mutation examples and unsafe path/code-execution
    counterexamples; it is design evidence, not a sandbox implementation

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
9. staged mutation, validation, commit, and rollback semantics

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
- Given a write target does not exist, authorization resolves and validates its
  nearest existing parent before creating any path component.
- Path authorization is repeated at the side-effect boundary or enforced by the
  sandbox backend so a symlink swap or other time-of-check/time-of-use change
  cannot redirect an approved operation outside the grant.

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
- Approval binds a fingerprint of the final normalized operation, including
  effective path, command/argv, working directory, environment policy, and
  staged changed-path manifest when present.

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
- An in-process `exec` call with filtered or unrestricted builtins must not be
  reported as sandboxed code execution. Code-execution exposure requires a
  backend that explicitly reports and enforces its isolation and resource
  capabilities.

### FR-6: Track workspace state and audit records

The runtime must make mutations inspectable.

Acceptance criteria:

- Each mutating action records changed paths, action id, tool id, node id, run id,
  approval id when applicable, and before/after metadata when available.
- Workspace persistence policy distinguishes ephemeral, in-memory, local-folder,
  and external-checkpoint workspaces when implemented.
- The runtime can report a summary of changed paths at workflow completion.
- Sensitive file content is not included in traces unless explicitly allowed.

### FR-7: Stage and commit mutations honestly

Backends that claim transactional workspace behavior must separate preparation
from durable mutation.

Acceptance criteria:

- A mutating action may prepare changes in an overlay, temporary workspace, or
  backend transaction without modifying the granted durable workspace.
- Validation evaluates the staged changed-path manifest, path grants, resource
  limits, and policy before approval.
- Approval binds the validated staged operation. Any changed path, content
  digest, command, or side-effect declaration invalidates the approval.
- Commit applies only the approved staged operation. Atomic commit is claimed
  only when the backend can enforce it; otherwise capability/status reports
  non-atomic or best-effort behavior before execution.
- Rollback before commit removes staged artifacts and leaves the durable
  workspace unchanged. A compensating action after commit is not called
  rollback and requires its own policy and approval.
- Returning `COMMITTED` or `ROLLED BACK` status text without enforcing the
  corresponding state transition must not satisfy this contract.

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
- Treat canonical path containment as a backend-enforced invariant, not a
  lexical prefix check on untrusted input.

## Future Work

Lanham's `AI Agents in Action, Second Edition` reinforces several production
safety concerns for future sandbox/workspace slices:

- egress controls for network-capable tools and MCP servers
- prompt-injection and data-exfiltration defenses at tool and workspace
  boundaries
- idempotency and replay declarations for mutating actions
- timeout, resource, and budget enforcement for long-running tools
- changed-path and side-effect summaries that can support incident review
  without exposing sensitive file contents

These follow-ups must remain behind explicit grants, approval policy, and
backend capability reporting.

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
- [ ] Absolute paths, nonexistent-target parent traversal, and symlink-swap
      attempts cannot escape a granted root.
- [ ] Read-only grants reject write, patch, and delete operations.
- [ ] Mutating actions produce approval interruptions by default.
- [ ] Resource limits are enforced or unsupported limits fail during preparation.
- [ ] Trace events include redacted audit records for mutating actions.
- [ ] Backend capability mismatch fails before execution.
- [ ] Staged validation and approval bind the exact operation later committed.
- [ ] Pre-commit rollback leaves the durable workspace unchanged.
- [ ] In-process `exec` cannot advertise sandboxed code-execution capability.
