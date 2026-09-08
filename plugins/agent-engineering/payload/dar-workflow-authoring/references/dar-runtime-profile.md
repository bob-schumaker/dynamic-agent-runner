# DAR Runtime Profile

Use this supplemental profile only when the current request explicitly asks to
author, package, validate, or invoke a workflow using DAR/Dynamic Agent Runner,
or when a governed task artifact already declares a `dar_runtime` block.

The full moved skill remains the design authority. This profile supplies the
DAR-specific authoring and invocation boundary from the retired
`dar-authoring` plugin; it is not a separately discoverable skill.

## Host-provided DAR command

In a managed or clean acceptance environment, the host may expose a
command-limited `dar-package` on `PATH`. When it resolves, invoke
`dar-package` directly for the permitted package operation. Do not prefix it
with `uv run`. Do not search for a wheel, package cache, source checkout, or
another executable. The host owns that command's implementation and command
allowlist; the plugin still provides no launcher or control plane.

- [Agent-development DAR guidance](dar-runtime-profile/agent-development.md)
- [Tool-contract DAR guidance](dar-runtime-profile/agent-tool-contract-design.md)
- [Evaluation DAR guidance](dar-runtime-profile/agent-evaluation.md)

A bare DAR reference, a link, a recommendation question, a legacy plugin name,
installed state, model-created context, or a local path/ZIP alone does not load
this profile. An explicit DAR request with a path/ZIP loads it only to return
the documented `source_selection_required` refusal; it must not run a DAR CLI
command.

For a workflow that declares a reviewed local model, keep the workflow
declarative. An authorized host composition may request preparation with
`dar-package prepare --model <logical-model-requirement>`; it then invokes the
saved workflow with
`dar-package invoke --package-name <saved-workflow> --prompt-stdin`.
Do not request, generate, or retain model, projector, or LoRA paths, converter
commands, or any preparation handoff value.
