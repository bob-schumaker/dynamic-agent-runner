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
service, manage credentials, or write package files itself. Run DAR's package
CLI directly through this pinned command:

<!-- rumdl-disable MD013 -->

```sh
uv run --no-project --python 3.14 --index-url https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple --with dynamic-agent-runner==0.2.1 dar-package version --json
```

<!-- rumdl-enable MD013 -->

When the host provides `dar-package` on `PATH`, use that command directly for
every package operation. Do not prefix it with `uv run` or search for a wheel;
the host command is the only permitted interface in that environment. Use the
pinned command above only when no host-provided `dar-package` is available.

For a local-wheel development check, replace the `--with` argument with the
absolute wheel path. Never use a project-relative wrapper, a state directory,
or an MCP control plane.

Confirm the DAR package is available before promising an authoring operation.
If a command returns an error, return `authoring_runtime_unavailable` rather
than creating an unvalidated package or substituting a legacy command.

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

For a bounded no-tool workflow, start from the plugin's `templates/` files.
Keep the runtime shape, graph entrypoint, output contract, descriptor limits,
and `dar_runtime` block intact; change only the package identity, human-facing
purpose, and the local-model system prompt needed for the defined task. The
runtime must retain `format_version: 1`, `package_type:
dynamic_agent_design`, `entrypoint: answer_request`, a single `llm_step` node
named `answer_request`, no tools, and the `final_answer` output contract. The
descriptor must retain `required_version: 0.2.1`, `allowed_tool_ids: []`, and
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

## Author a package

A human must first select the material files and issue the host-owned manifest.
Accept only the resulting opaque `material_set_id`; do not issue material, pass
a local path, or provide raw material content. The project command is the sole
command that may return approved material content; use that content transiently
and do not repeat it in the handoff.

<!-- rumdl-disable MD013 -->

```sh
uv run --no-project --python 3.14 --index-url https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple --with dynamic-agent-runner==0.2.1 dar-package project-authoring-materials --material-set-id <opaque-id>
uv run --no-project --python 3.14 --index-url https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple --with dynamic-agent-runner==0.2.1 dar-package create-authored-package --package-name <user-requested-name>
uv run --no-project --python 3.14 --index-url https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple --with dynamic-agent-runner==0.2.1 dar-package write-authored-package-file --authoring-output-id <opaque-id> --relative-path <package-relative-path> --content-stdin
uv run --no-project --python 3.14 --index-url https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple --with dynamic-agent-runner==0.2.1 dar-package finalize-authored-package --authoring-output-id <opaque-id> --material-set-id <opaque-id>
```

<!-- rumdl-enable MD013 -->

Create the output once, write only `agent-design.md`, `agent-runtime.yaml`,
`agent-graph.mmd`, `workflow-descriptor.yaml`, and declared package assets, and
finalize with the same material-set ID. Do not pass paths, credentials, model
profiles, connection settings, source handles, or registration IDs. Finalizing
validates the package but does not select or register it; report any required
human host handoff separately.

## Handoff

Return the finalized package name and redacted finalization receipt, its
input/output contract, required model profile, and any host-owned capability
setup. Explain that the human host must select and register the finalized
package before a later request can invoke its saved name. Do not turn the
package into a general-purpose interactive tool.

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
