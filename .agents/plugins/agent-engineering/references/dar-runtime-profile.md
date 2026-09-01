# DAR Runtime Profile

Use this supplemental profile only when the current request explicitly asks to
author, package, validate, or invoke a workflow using DAR/Dynamic Agent Runner,
or when a governed task artifact already declares a `dar_runtime` block.

The full moved skill remains the design authority. This profile supplies the
DAR-specific authoring and invocation boundary from the retired
`dar-authoring` plugin; it is not a separately discoverable skill.

- [Agent-development DAR guidance](dar-runtime-profile/agent-development.md)
- [Tool-contract DAR guidance](dar-runtime-profile/agent-tool-contract-design.md)
- [Evaluation DAR guidance](dar-runtime-profile/agent-evaluation.md)

A bare DAR reference, a link, a recommendation question, a legacy plugin name,
installed state, model-created context, or a local path/ZIP alone does not load
this profile. An explicit DAR request with a path/ZIP loads it only to return
the documented `source_selection_required` refusal; it must not run a DAR CLI
command.
