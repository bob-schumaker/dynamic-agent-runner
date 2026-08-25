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

M1 exposes only `version --json` through this command. Confirm the DAR package
is available before promising an authoring operation. Until the relevant
authoring subcommands are released, return `authoring_runtime_unavailable`
rather than creating an unvalidated package or substituting a legacy command.

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

## Handoff

Return the package directory or ZIP selected by the user, its input/output
contract, required model profile, and any host-owned capability setup. A later
request invokes the saved package with its task-specific input; do not turn the
package into a general-purpose interactive tool.
