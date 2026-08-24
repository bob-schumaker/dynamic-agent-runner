# Sandbox and Workspace Runtime Specification

## Metadata

- Feature slug: `sandbox-workspace-runtime`
- Mode: `light`
- Artifact type: future feature specification
- Status: DAR approval-policy boundary and a host-only descriptor-relative
  no-follow file-copy primitive are implemented; all writable model-facing
  runtime surfaces remain deferred, including the planned host-wrapper
  temporary-workspace profile and DAR-authoring file-ingress integration
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related runtime surfaces:
  - `runtime.execution_policy.sandbox_runtime`
  - opt-in read-only `local_workspace` built-in tool pack
  - tool policy metadata: `tool_type`, `side_effect`, `approval_required`,
    `sandbox`
  - approval interruption (implemented); continuation/resume remains future work
- Evaluated supporting reference:
  - `https://github.com/MARKTECHPOST-AI-MEDIA-INC/AI-Agents-Projects-Tutorials`
    includes useful staged-mutation examples and unsafe path/code-execution
    counterexamples; it is design evidence, not a sandbox implementation
  - `https://mathspp.com/blog/write-a-coding-agent-from-first-principles`
    shows the minimal coding-agent tool progression from read-only file access
    to write/edit tools, shell execution, tool-result error flags, and
    approval-before-command execution. It is tutorial evidence, not a
    production safety or sandbox pattern.

## Objective

Define a future sandbox/workspace runtime that can safely expose write, patch,
shell, code-execution, and mounted-workspace capabilities to workflows under
explicit path grants, resource limits, approval policy, and observable runtime
boundaries.

## Existing Baseline

The current runtime preserves sandbox/workspace metadata and provides an opt-in
read-only local workspace pack. Its host-only
`copy_regular_file_no_follow(...)` primitive copies one selected regular file
from a trusted absolute input root into a fresh private workspace through
descriptor-relative `O_NOFOLLOW` handles, enforces a byte limit, commits the
copy atomically, and returns only destination-relative path, SHA-256, and byte
count. It intentionally does not provide write tools, shell tools, apply-patch
tools, package installation, workspace persistence, or model-facing sandbox
enforcement. The primitive is not yet wired into a DAR-authoring input artifact.

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

The council review recommends pairing a future DAR-native sandbox slice with
`approval-interruption-resume` before broad MCP, loop, or interpreter execution.
It should not attempt a full sandbox platform: start with explicit path grants,
one or two mutating workspace tools, approval interruption before side effects,
and a redacted changed-path summary.

## V1 Paired Slice Boundary

The first paired implementation slice does not add write, patch, delete, shell,
package-install, or mounted-workspace tools. It contributes the approval policy
side of sandbox safety by proving that approval-required direct tool actions
pause before any side effect.

This is the DAR-core boundary. The separately shipped wrapper workspace profile
defined below is a host-owned convenience surface; it must not be represented as
an implemented DAR `sandbox_runtime` or weaken this core v1 boundary.

This keeps the first slice small enough to validate without introducing a host
sandbox backend. Later sandbox slices can add explicit workspace grants and
mutating tools behind the approval boundary created by
`approval-interruption-resume`.

Implemented from this paired slice:

- direct approval-required tool steps pause before invocation
- no registered handler side effect occurs before approval
- approval pause traces mark requested arguments as sensitive
- capability status can report the live approval boundary

Still deferred from DAR core:

- write, patch, delete, shell, package-install, and mounted-workspace built-ins
- explicit writable workspace grants and path authorization
- sandbox adapters and resource enforcement
- changed-path audit records for real workspace mutations

## Future DAR-Native Coding-Agent Tool-Pack Boundary

The mathspp coding-agent reference reinforces a concrete product pressure: a
coding agent is not useful for code changes until it can mutate source files and
run verification commands. This is a future DAR-native capability, separate from
the host-wrapper scratch profile below.

The first coding-agent-oriented slice belongs in this spec and should be small:

- explicit writable path grants rooted in caller-approved workspaces
- one or two mutating source-file tools, such as `write_file` plus
  `replace_text` or `insert_lines`
- changed-path audit records and bounded model-facing results
- approval-required behavior by default for mutating actions
- focused fake tests for path containment, approval pause, redaction, and
  changed-path reporting

Verification command support also belongs here, but it should start narrower
than arbitrary shell: allowlisted tools such as `run_tests` or `run_linter` with
fixed working-directory rules, timeouts, output caps, and side-effect metadata.
General `bash` or shell-string execution remains a later, higher-risk command
capability.

A separate future `coding-workspace-tool-pack` feature spec may be useful if
the registry/tool-pack API, model-facing schemas, aliases, or product ergonomics
grow large enough to obscure this spec's sandbox policy. If created, that spec
should depend on `sandbox-workspace-runtime` and `approval-interruption-resume`;
it should own tool-pack naming and model-facing contracts, not path grants,
approval binding, backend isolation, or resource enforcement.

## Planned Interactive Wrapper Scratch Workspace

The DAR workflow wrapper can later provide an interactive scratch surface. This
planned, host-owned slice is enabled only when the wrapper profile/catalog
exposes its fixed tools: DAR invokes those registered tools, while the wrapper
owns the workspace root, path authorization, mutation semantics, and audit
store. It does not make `sandbox_runtime` live inside DAR or add a DAR default
write capability. This interactive scratch surface is not a prerequisite for the
DAR authoring plugin's no-tool base or trusted file-ingress slice; file-backed
workflow invocations instead depend on the separate ingress contract below.

Each run may obtain a fresh tenant-scoped scratch root through
`get_temporary_workspace()`. The tool returns an opaque virtual root URI such
as `workspace://<workspace-id>/`, allowed capabilities, and expiry metadata; it
never returns an absolute host path, physical root, or host filesystem identity.
The wrapper maps a virtual URI to its physical scratch root only while handling
the tool call. The initial surface is:

- `get_temporary_workspace()`;
- `read_file`, `list_files`, and `search_files`, each accepting a virtual path;
- `write_file(virtual_path, content, precondition)`, where `precondition` is
  either `{kind: absent}` or `{kind: hash, value: <digest>}`;
- `replace_text(virtual_path, old_text, new_text, expected_occurrences,
  expected_hash)`;
- `delete_file(virtual_path, expected_hash)`, limited to one regular file; and
- `changed_paths(workspace_uri)`.

Virtual paths use the canonical form
`workspace://<workspace-id>/<relative-posix-path>`. The wrapper uses an exact
ASCII wire parser, not a generic URI host parser: `workspace-id` is a fixed
lower-case base32 CSPRNG identifier, and file paths contain one or more nonempty
POSIX segments without percent encoding, backslashes, control characters, `.`,
or `..`. The root URI is valid only for workspace-scoped operations such as
`changed_paths`; file tools require a nonempty relative path. Reject every other
scheme, authority decoration, query, fragment, or path form before any URI
normalization. Tenant, run, and workspace identity come from the trusted wrapper
invocation context, never model-provided arguments; IDs are unguessable and
never derived from that identity. Path fields in tool results and audit records
expose virtual paths only. `read_file` returns only bounded UTF-8 text or fails;
traces and audit records do not contain its content.

The initial surface does not expose physical workspace paths:

- neither model prompts nor tool schemas receive a host root;
- a virtual path cannot be used as a host path outside the wrapper; and
- all physical path resolution occurs after tenant, run, expiry, and virtual URI
  validation at the wrapper's side-effect boundary.

### First Wrapper Prerequisite: Trusted File Ingress

Some wrapper invocations need a caller-selected local input before a model runs,
such as an HTML body for an email workflow. This is not a
model-facing file-path tool and does not register the interactive scratch tools
above. The trusted wrapper CLI or control plane may accept a physical source
path only from its own caller, validate it against a configured input root with
the same descriptor-relative no-follow primitive, then copy the opened regular
file into a fresh private temporary workspace. It returns only an opaque,
hash-bound input-artifact identifier and byte count to the workflow runner;
the source path never enters a model prompt, tool schema/result, trace, approval
record, or audit record.

Ingress applies the configured type, encoding, request-size, and file-byte limits
before accepting the artifact. It streams the exact opened source descriptor once
into the private temporary file while hashing that byte stream, then commits the
copy atomically. The implementation validates the configured encoding only from
that private copy; in the initial profile every `text/*` input is strict UTF-8.
It then binds the hash to the opaque artifact identifier and invocation. The
subsequent handler reads only that private copy. A host cannot claim
path-contained or symlink-safe body-file support if it rewinds or reopens the
source path after validation or lets the model supply the physical source path.

The DAR authoring plugin's file-backed workflow invocations depend on this
ingress slice. Until its positive tests pass, an invocation that accepts a local
file must be unavailable even when its external tool binding is configured.

The workspace capability is bound to its issuing invocation; another run or
tenant cannot use it. The wrapper serializes mutations per workspace and
evaluates every expected-hash precondition while holding that mutation lock.
Reads, listings, and searches are bounded by configured file bytes, entries,
recursion depth, result bytes, match count, and snippet bytes; search is
literal-only with a bounded query length, and all reads return UTF-8 text only.
They enumerate no symlink and return no physical path. The planned interactive
slice has no aggregate workspace-size quota; that remains the explicitly
deferred follow-up listed below.

`workspace_tool_auto` is an explicit trusted policy that may disable per-tool
prompting only for this fixed surface and its approved path grants. Its binding
includes the exact tool identifier and schema version, workspace root, operation
limits, and—when a prebuilt workflow supplies one—the virtual path and expected
content hash. It cannot authorize an alias, delegated capability, external
export, or copying workspace contents to a durable or network destination. The
DAR authoring plugin's separate `workflow_auto` policy governs its approved
workflow external-tool surface under its FR-6; neither policy changes DAR's independent
`approval_required` metadata. `--ask` overrides `workspace_tool_auto` with the
wrapper approval broker, which displays the virtual path, operation, byte count,
and pre/post hashes and rejects a stale operation. Neither mode adds a broader
workspace capability.

`write_file` creates or replaces one regular file only when its optimistic
concurrency precondition holds. `replace_text` changes one known file only when
the caller-provided occurrence and content-hash expectations match.
`delete_file` removes one regular file only when its expected hash matches; it
does not recursively delete directories. These tools neither create directory
trees, follow symlinks, apply arbitrary patches, run commands, install packages,
nor access the network. Separate capabilities must add those actions later.

All wrapper write implementations must:

- use one descriptor-relative, no-follow filesystem primitive for every path
  component (including reads, listings, searches, deletion, and cleanup): open
  each parent relative to an already validated directory handle, reject
  symlinks, devices, and non-regular final entries with handle metadata, and
  create/rename/unlink through the validated parent handle. `Path.resolve()` or
  a pre-check followed by ordinary path I/O does not satisfy this requirement;
  a platform without these primitives must expose the write profile as
  unavailable;
- enforce maximum file bytes, write bytes, changed-path count, and UTF-8/text
  policy before mutation;
- write a temporary file in the authorized target directory, flush the file and
  directory where the backend supports it, and atomically replace the target
  only within that same directory/filesystem; and
- record path, pre/post content hashes, byte counts, operation ID, run ID, and
  status in the audit store without recording raw file content in traces or
  model-facing results.

Workspace roots and child directories are wrapper-owned and owner-only; the
wrapper retains the root directory handle and verifies ownership/mode before
use. The expected-hash contract assumes no untrusted co-writer can rename an
entry inside that root. A hostile same-UID host process is out of scope for this
in-process profile; a host that cannot establish private ownership must expose
the profile as unavailable or use an OS-isolated backend.

Temporary workspaces expire at run completion or their configured TTL. On expiry
or completion the wrapper atomically changes state from `active` to `closing`
under the workspace state lock, denies new leases, and requires each in-flight
lease to recheck active state immediately before mutation. Each operation has a
bounded deadline. Cleanup runs after leases drain or the deadline expires; the
latter outcome quarantines the handle and root from all access. Cleanup uses the
same descriptor-relative no-follow traversal and records `deleted` or a redacted
quarantine failure. A workspace ID/root is never recreated, reused, or rebound;
an expiry race fails before mutation.

`changed_paths(workspace_uri)` returns a bounded list of changed virtual paths,
opaque content-version tokens, byte counts, and operation status, sorted
deterministically with an explicit truncation/continuation signal. It never
returns raw file contents or cryptographic content hashes. Protected audit
records retain path, hashes, byte counts, and operation status.

Each mutation has a durable operation ID and an intent record before mutation.
Audit storage uses an append-only write interface with access control; tamper
evidence is a later audit feature. Where its store supports transactions, the
wrapper atomically records completion with the mutation outcome. Otherwise, a
completion failure or startup-detected unresolved intent produces an explicit
`audit_incomplete`/indeterminate status; `changed_paths` must surface that state
rather than report normal success. A backend that cannot provide the stated
atomic replacement semantics must report that capability as unavailable rather
than claim an atomic write.

## Functional Requirements

### FR-1: Require explicit workspace grants

The runtime must not expose writable workspace capabilities without explicit
caller or deployment configuration.

Acceptance criteria:

- Given no DAR runtime grant or wrapper profile/catalog exposure, write and shell
  tools are unavailable even if a workflow references them.
- Given a workspace root is granted read-only, write, patch, and delete actions
  fail closed.
- Given a workspace root is granted writable access, write actions are still
  restricted to paths inside the granted root.
- Given a path includes symlinks, traversal, or relative components, validation
  rejects it before authorization.
- Given a write target does not exist, authorization resolves and validates its
  nearest existing parent before creating any path component.
- Path authorization is repeated at the side-effect boundary or enforced by the
  sandbox backend so a symlink swap or other time-of-check/time-of-use change
  cannot redirect an approved operation outside the grant.
- The out-of-the-box wrapper write tools resolve and open targets without
  following symlinks, and create a target only below an already authorized,
  existing parent directory.
- The wrapper binds a temporary workspace to trusted current tenant/run identity,
  not tool arguments, and rejects cross-run and cross-tenant use.

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
- The out-of-the-box wrapper write slice exposes only `write_file`,
  `replace_text`, `delete_file`, and `changed_paths` inside a temporary
  workspace; it does not infer patch, command, package-install,
  directory-creation, network, or shell permission.

### FR-3: Apply approval policy to mutating or risky actions

Mutating workspace actions must integrate with approval policy.

Acceptance criteria:

- Write, delete, patch, package-install, network, and shell actions default to
  approval-required unless an explicit trusted policy disables approval.
  `workspace_tool_auto` is such an exception only for its exact catalog-bound
  scratch operations.
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
- The out-of-the-box wrapper tools enforce text/encoding policy and expected
  content-hash or absence preconditions before replacing a file.
- Read, list, and search operations enforce bounded traversal, entries, source
  bytes, result bytes, match count, and snippet bytes before returning a result.
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
- Wrapper write audit records include only virtual path, pre/post content hash,
  byte count, operation status, and correlation identifiers by default; raw file
  content and physical filesystem paths are excluded from traces, events, and
  model-facing results.
- Audit records are append-only and ordered. Audit-intent persistence is checked
  before mutation; an unavailable completion record returns an explicit
  indeterminate audit result rather than a successful mutation result.
- Workspace cleanup transitions through active, closing, deleted, or quarantined
  state. A cleanup failure denies all access, preserves only a redacted internal
  record, and retries without reusing the workspace identity or root.
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

- No DAR default write or shell capability; the separately configured wrapper
  scratch profile may expose only its fixed temporary-workspace tools.
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
- For a surface described as symlink-safe, require descriptor-relative,
  no-follow traversal at every filesystem operation; pre-resolution with a path
  library is not sufficient against a concurrent symlink swap.
- Keep temporary-workspace expiry and cleanup under wrapper lifecycle control;
  a model cannot renew, revive, or rebind an expired handle.

## Future Work

Lanham's `AI Agents in Action, Second Edition` reinforces several production
safety concerns for future sandbox/workspace slices:

- egress controls for network-capable tools and MCP servers
- a per-workspace total-size quota, including quota reservation and deterministic
  failure when writes would exceed the configured aggregate byte limit
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
- Should a future `coding-workspace-tool-pack` split out model-facing tool-pack
  ergonomics after the first write/edit slice, or should the tool-pack contract
  remain embedded here?
- What path-grant format should callers use?
- What default approval policy should a future DAR-native write, patch, delete,
  shell, network, or package-install tool use? (The wrapper scratch profile uses
  catalog-bound `workspace_tool_auto` unless `--ask` is selected.)
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
- [ ] A parent-directory symlink swap between validation and mutation cannot
      redirect read, write, delete, listing, search, or cleanup outside the
      workspace.
- [ ] Absolute paths, nonexistent-target parent traversal, and symlink-swap
      attempts cannot escape a granted root.
- [ ] Read-only grants reject write, patch, and delete operations.
- [ ] Mutating actions produce approval interruptions by default, except for an
      explicitly trusted `workspace_tool_auto` operation.
- [ ] Resource limits are enforced or unsupported limits fail during preparation.
- [ ] Trace events include redacted audit records for mutating actions.
- [ ] Backend capability mismatch fails before execution.
- [ ] Staged validation and approval bind the exact operation later committed.
- [ ] Pre-commit rollback leaves the durable workspace unchanged.
- [ ] In-process `exec` cannot advertise sandboxed code-execution capability.
- [ ] Wrapper `write_file` and `replace_text` reject traversal, symlink, device,
      non-regular-file, missing-parent, size-limit, encoding, and stale-hash
      inputs before mutation.
- [ ] `get_temporary_workspace()` returns an opaque, tenant-scoped virtual root
      URI rather than an absolute host path; its expiry invalidates all
      subsequent access.
- [ ] Trusted file ingress rejects an out-of-root, symlinked, non-regular,
      oversized, invalid-encoding, or parent-swap source and returns only a
      hash-bound opaque input-artifact identifier for an accepted private copy.
- [ ] Concurrent source modification during trusted file ingress cannot change
      the copied byte stream after its protected hash is bound to the operation.
- [ ] Malformed, encoded, guessed, replayed, cross-run, and cross-tenant
      workspace URIs fail closed without exposing a physical path.
- [ ] The root URI is accepted only for workspace-scoped operations; file tools
      reject it, mixed-case identifiers, and every non-canonical wire form.
- [ ] `delete_file` can remove only a hash-matched regular file inside the
      temporary workspace and cannot delete a directory or escape the grant.
- [ ] Wrapper writes use same-filesystem temporary replacement and report an
      unavailable capability when atomic replacement cannot be guaranteed.
- [ ] Competing mutations serialize, evaluate their hash preconditions inside
      the lock, and cannot both report success for the same stale content.
- [ ] Expiry races deny the mutation; cleanup invalidates first, never reuses an
      ID/root, and quarantines access if no-follow cleanup fails.
- [ ] Expiry during a read, write, or hung search cannot extend access past the
      operation deadline or block the closing-to-quarantine transition forever.
- [ ] Forced audit-intent or audit-completion failure cannot produce an
      unqualified successful mutation result.
- [ ] Startup reconciliation marks an unresolved audit intent as
      `audit_incomplete`; `changed_paths()` does not report normal success.
- [ ] A private-root ownership/mode failure or externally raced final entry makes
      the in-process profile unavailable rather than claiming hash preconditions.
- [ ] `changed_paths()` returns only bounded virtual paths, opaque content-version
      tokens, byte counts, and operation status; it never returns raw file
      content, a cryptographic content hash, or a physical path.
