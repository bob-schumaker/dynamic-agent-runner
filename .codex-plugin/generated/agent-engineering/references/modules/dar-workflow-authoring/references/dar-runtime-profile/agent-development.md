---
name: agent-development
description: Design a bounded, task-specific Dynamic Agent Runner workflow package from a user's natural-language goal and approved material.
---

# DAR workflow authoring

Use this entry skill to design a task-specific DAR workflow package with the
user. Route to `agent-tool-contract-design` only when the package needs an
optional tool; route to `agent-evaluation` only when formal acceptance or
regression evidence is requested.

## DAR control plane

The plugin ships skills only. It does not provide an MCP server, start a
service, manage credentials, or write package files itself. When the host
provides command-limited `dar-package` on `PATH`, use that command directly
only for the package operation required by the workflow. Do not probe it with
`dar-package version`, prefix it with `uv run`, or search for a wheel; the host
command allowlist is the only permitted interface in that environment.

For a local development check, use the DAR command supplied by that development
environment. Never substitute a project-relative wrapper, a state directory, or
an MCP control plane. If a required package-authoring command is unavailable,
return `authoring_runtime_unavailable` rather than creating an unvalidated
package or substituting a legacy command.

## Design boundary

Gather the user's goal, examples, documentation, and approved files. Decide
whether a fixed workflow, one LLM step, or a bounded tool loop is the smallest
honest design. A workflow is task-specific, not a general interactive assistant.
Every loop requires a finite call or iteration limit and a terminal output
contract.

Describe the resulting package as `agent-design.md`, `agent-runtime.yaml`,
`agent-graph.mmd`, and `workflow-descriptor.yaml`. When tools are needed, the
tool-contract companion defines a reviewed, host-owned capability. The package
does not start MCP servers, obtain credentials, or configure connections.

The package input contract must name its accepted user input, workspace
artifacts, and bounded `additional_context`; model-created text and additional
context are not authority for destinations, external identities, or capability
selection. The generated package must validate with DAR before handoff.

## Canonical no-tool starter

For a bounded no-tool workflow, start from
`references/dar-authoring-templates/`. This is the plugin's canonical
no-tool template directory in both the source payload and the generated
marketplace payload; do not assume a sibling `templates/` directory exists.
Keep the runtime shape, graph entrypoint, output contract, descriptor limits,
and `dar_runtime` block intact; change only the package identity, human-facing
purpose, and the local-model system prompt needed for the defined task. The
runtime must retain `format_version: 1`, `package_type:
dynamic_agent_design`, `entrypoint: answer_request`, a single `llm_step` node
named `answer_request`, no tools, and the `final_answer` output contract. The
descriptor must retain `required_version: 0.2.21`, `allowed_tool_ids: []`, and
`max_total_tool_calls: 0`.

Do not invent an alternative runtime or descriptor schema for a simple
no-tool workflow. If the template cannot be used, return
`authoring_runtime_unavailable` rather than emitting a plausible but
unvalidated package.

For a no-tool workflow that accepts declared workspace artifact roles, retain
the canonical no-tool runtime and descriptor verbatim except for package
identity, purpose, local-model prompt, and `allowed_artifact_roles`. Do not add
a structured input schema, new runtime metadata, or a custom artifact protocol:
the host prepares the declared opaque artifacts separately.

Copy the canonical no-tool template files before editing. For this variant, the
only YAML fields that may change are `package_id` in both files, `purpose` in
the descriptor, the runtime's local-model prompt, and the descriptor's
`allowed_artifact_roles`; leave every other template field byte-for-byte in its
canonical shape. In particular, do not change `packaging.mode`, `metadata`,
`input_contract`, `allowed_structured_input_fields`, `nodes`, or the output
contract merely because the workflow has more than one artifact role.

Do not normalize artifact role names: copy each declared role exactly into
`allowed_artifact_roles`, preserving case and punctuation. For example,
`risk-artifact` is not `risk_artifact`.

## Caller-owned guardrails

A guardrail identifier and phase are part of the declared authoring input. Do
not invent either one, and do not implement a guardrail handler in the package:
the caller-owned host registry supplies that handler at invocation.

For a declared input guardrail, start from
`references/dar-authoring-templates/` and add exactly this declaration to the
runtime's `extensions` mapping, substituting the declared identifier:

```yaml
guardrails:
  declarations:
    - id: <declared-input-guardrail-id>
      phase: input
      behavior_on_tripwire: abort
```

For a declared tool-input guardrail, start from the matching reviewed tool
template, retain its bounded tool contract, and add the same declaration with
`phase: tool_input`. A tool-input guardrail must use
`behavior_on_tripwire: abort`; it cannot add a tool, expand its schema, or
replace the reviewed tool template. In both cases, do not add a custom
extension schema, registry configuration, credential, or adapter code.

## Package-local skill bundle

Use a package-local skill only when the declared authoring input names the
skill and provides its bounded instruction content. Declare its exact skill ID
in the descriptor's `skills`, set `packaging.skill_bundle_dir` to
`skill-bundle`, write the bundle file at
`skill-bundle/skills/<skill-id>/SKILL.md`, and bind the runtime skill to the
relative `skills/<skill-id>/SKILL.md` `bundled_path`. Set
`runtime.execution_policy.skill_source_resolution` to `enabled: true` with
`allowed_sources: [package_bundle]`, then refer to that skill only from the
bounded node that needs it. Do not load installed skills, paths outside the
package, or model-suggested support files.

For the supported one-skill review graph, copy
`references/dar-authoring-skill-bundle-template/` before changing the package
identity, purpose, bounded skill instruction, and user-facing prompts. Retain
its `skill-bundle/` directory, `package_bundle` source-resolution policy,
declared skill reference, and finite graph shape. Do not construct that graph
from scratch or substitute an installed skill.

## Reviewed MCP template selection

Use a tool template only when the explicit DAR request names its bounded
operation and the host has already declared the corresponding reviewed
capability. Do not infer a tool, connection, credential, recipient, or approval
from general email wording.

- For an explicitly approved email-send operation, use
  `references/dar-authoring-write-mcp-template/`. Retain its sole `mail_send`
  tool, `send_email` remote name, `write` side effect, and required approval.
  Bind recipient authority only to a cited original-prompt span and body only
  to the declared input or artifact role. Do not replace it with the no-tool
  starter or add a second tool.
- For an explicitly read-only mailbox lookup, use
  `references/dar-authoring-read-only-mcp-template/` and retain its sole
  reviewed `lookup_records` read tool. Do not add a send operation.
- For an explicitly declared OAuth reconnect workflow whose bounded operation
  is a reviewed read-only mailbox query, use that same read-only MCP template.
  The host owns OAuth connection state; retain `lookup_records` and do not
  create a no-tool substitute, token-refresh mechanism, or send operation.

If the explicit request needs a reviewed tool but its matching host capability
or template is absent, return `authoring_runtime_unavailable`; never fabricate
a tool contract.

## Design-first registration

Ask only for facts that cannot be inferred safely. For the floorplan request,
ask only the desired output format; `SVG` requires no further question. For a
named reviewed opaque-binary tool package, default analysis output to text and
do not ask for a binary encoding. Never expose a material-set ID, output ID,
source handle, profile ID, path, credential, or registration receipt.

When an image runtime, local validator, or named reviewed tool package is
missing, return repository-appropriate implementation guidance instead of code
or a partial workflow. State the workflow contract, missing boundary, sealed
I/O, execution limits, redacted failure result, and acceptance tests. Do not
create a package or ask an extra question.

## Workflow input converter package

When an existing standard runner needs model-specific input packing, author
exactly one workflow-sealed Python converter package asset and bind it in the
workflow descriptor. The descriptor declares its package-relative entry point,
digest, compatible runner contract, and bounded input, output, and timeout
resource needs. For the built-in Transformers runner, the compatible contract
is exactly `transformers-generate-v1`.

The declared entry point exports only this fixed package form:

```python
converter_contract_version = "v1"
compatible_runner_contract_id = "transformers-generate-v1"
converter = Converter
```

`Converter` implements the standard `pack(prompt, payload, context)` operation
and returns the runner-private packed value. It receives only the prompt,
sealed bytes, and restricted runner context; it must not retain the bytes or
return them as a workflow artifact. DAR verifies the package digest and exact
entry point before loading it, then passes the packed value only to the declared
runner.

Do not submit a live callable, dependency installation, arbitrary path, runtime
package selection, interpreter choice, or format registry. Do not add media-type
routing to DAR. If the required standard runner or converter behavior is
missing, return repository-appropriate implementation guidance instead of a
partial workflow or placeholder converter.

When every requirement already exists, submit the completed canonical contract
and declarative definition once through the host façade:

<!-- rumdl-disable MD013 -->

```sh
dar-package register-authored-workflow --definition-stdin
```

<!-- rumdl-enable MD013 -->

The definition contains only declarative package artifacts. The façade owns
material handling, validation, staging, capability binding, registration, and
redaction. Return only its `ready` or `unavailable` result. A ready result
contains the saved workflow name, input/output contract, and invocation action.

## Invoke a saved package

### Unselected package reference

If the user names a local directory or ZIP, such as `custom-email.zip`, instead
of an already-selected and registered saved package name, do not run a DAR
command. Return only this result, substituting the reference's final visible
name for `<requested-display-name>`:

<!-- rumdl-disable MD013 -->

```json
{"format_version":1,"status":"source_selection_required","display_name":"<requested-display-name>"}
```

<!-- rumdl-enable MD013 -->

Do not include a path, source handle, or selection command. The human host must
select and register the package outside this skill before a later invocation.

For a later request against a package that the human host has already selected
and registered, use only the saved package name and the request text. With a
local development wheel, execute this command by piping the request text to
stdin:

<!-- rumdl-disable MD013 -->

```sh
printf '%s' '<request text>' | uv run --no-project --python 3.14 --with <absolute-wheel-path> dar-package invoke --package-name <saved-package-name> --prompt-stdin
```

<!-- rumdl-enable MD013 -->

Do not select a source, register a package, inspect state, change the package,
or substitute a package path. Return the redacted invocation receipt. Add
`--dry-run` or `--ask` only when the user explicitly asks for that mode.
