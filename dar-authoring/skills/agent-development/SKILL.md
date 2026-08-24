---
name: agent-development
description: Design a bounded, task-specific Dynamic Agent Runner workflow package from a user's natural-language goal and approved material.
---

# DAR workflow authoring

Use this skill to design a task-specific DAR workflow package. It is the entry
skill for this plugin. Route to `agent-tool-contract-design` only when the
package needs an optional tool; route to `agent-evaluation` when formal
acceptance or regression evidence is requested.

## Input boundary

Accept a natural-language goal and any supplied examples, documentation, or
files through the host-owned authoring control plane. Call
the `dar-workflow` wrapper at `../../scripts/dar-workflow`, resolved relative to
this loaded `SKILL.md` file (never relative to the project cwd). Call it with
`issue-authoring-materials --materials-json-stdin` with only the material the
user supplied for this design; its receipt is an `AuthoringMaterialSet`. Then
call the same wrapper's
`project-authoring-materials` with the returned opaque `material_set_id`.
Each JSON member has exactly `role`, `content`, and `disposition`. Use
`reference_only` for the user's goal, examples, documentation, and files;
use `distributable` only when the user explicitly authorizes that material to
be included in the generated package.
Members are bounded and principal/expiry bound. Do not request or emit source
paths, credentials, connection secrets, or unselected material.

Call the wrapper's `create-authored-package` with the requested package name.
Keep its opaque `authoring_output_id` and use its
`write-authored-package-file --content-stdin` command for each generated
artifact. Do not write package files through a physical path or reuse a prior
output directory.

Decide whether a fixed workflow, one LLM step, or a bounded tool loop is the
smallest honest design. A workflow is task-specific, not a general interactive
assistant. Every loop has a finite step or iteration limit and a terminal output
contract.

For a tool-free workflow, start from the four files in `../../templates`, also
resolved relative to this `SKILL.md` file. Adapt the package id, purpose,
model-profile requirement, prompt, graph labels, input contract, and output
contract to the request; retain the finite no-tool invocation pattern. Do not
copy `package-manifest.json`: finalization creates it after the four authored
files are written through the control plane.

## Output

Before writing a package, require the host's DAR loader and authoring control
plane. If the control plane is unavailable, do not emit an unvalidated package
or invent its manifest; return the deliberate refusal
`authoring_runtime_unavailable` and name the missing host capability.

Generate a package directory containing:

- `agent-design.md`
- `agent-runtime.yaml`
- `agent-graph.mmd`
- `workflow-descriptor.yaml`
- `package-manifest.json`

The descriptor defines the package purpose, local model-profile requirement,
hybrid input contract, bounded `additional_context`, accepted workspace artifact
roles, terminal output schema, and every optional capability. Use DAR-supported
nodes and validate the package with the DAR loader before presenting it. Call
the wrapper's `finalize-authored-package` with `authoring_output_id` and
`material_set_id` to write the deterministic manifest and verify
private-material exclusion. Do not invent manifest digests or return an
unfinalized directory as a workflow package.

For a tool-free task, emit no tools and no skills. For optional tooling, name
only a reviewed host-owned tool capability in the descriptor; the package does
not start servers, obtain credentials, or configure an MCP connection. Explain
that a human later configures, reviews, and binds the connection before a saved
workflow can run.

## Handoff

Return the configured-root package name or archive selected by the caller, its
manifest and descriptor digests, the required host capabilities, and any
deliberate refusal. A later request invokes the saved directory with
`../../scripts/dar-workflow invoke --package-name <package-name>`. For local
wheel verification only, set `DAR_AUTHORING_DAR_WHEEL` to the exact absolute
wheel path before calling the wrapper. Do not invoke `run_dar_workflow` while
authoring.
