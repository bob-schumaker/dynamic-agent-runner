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
uv run --no-project --python 3.14 --index-url https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple --with dynamic-agent-runner==0.1.16 dar-package version --json
```

<!-- rumdl-enable MD013 -->

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

## Author a package

A human must first select the material files and issue the host-owned manifest.
Accept only the resulting opaque `material_set_id`; do not issue material, pass
a local path, or provide raw material content. The project command is the sole
command that may return approved material content; use that content transiently
and do not repeat it in the handoff.

<!-- rumdl-disable MD013 -->

```sh
uv run --no-project --python 3.14 --index-url https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple --with dynamic-agent-runner==0.1.16 dar-package project-authoring-materials --material-set-id <opaque-id>
uv run --no-project --python 3.14 --index-url https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple --with dynamic-agent-runner==0.1.16 dar-package create-authored-package --package-name <user-requested-name>
uv run --no-project --python 3.14 --index-url https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple --with dynamic-agent-runner==0.1.16 dar-package write-authored-package-file --authoring-output-id <opaque-id> --relative-path <package-relative-path> --content-stdin
uv run --no-project --python 3.14 --index-url https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple --with dynamic-agent-runner==0.1.16 dar-package finalize-authored-package --authoring-output-id <opaque-id> --material-set-id <opaque-id>
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
