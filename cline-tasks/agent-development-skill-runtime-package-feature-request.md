# Agent-development skill runtime-package feature request handoff

## Goal

- Provide a project-facing handoff for the agent-development skill repository that
  captures upstream changes requested by the `dynamic-agent-runner` runtime-package
  simplification analysis.
- Target upstream artifact:
  `/Users/roschuma/Repos/roschuma/clinerules-roschuma/skills/agent-development-skill/references/agent-runtime-package.md`

## Handoff Role

- Type: `external/project-facing handoff`
- Audience: future Cline session or maintainer working in the
  `clinerules-roschuma` agent-development skill repo
- Authority: supporting feature-request handoff for upstream skill/reference
  updates; the source analysis in
  `cline-tasks/agent-runtime-package-simplification-analysis.md` remains the
  local evidence bundle for this request
- Paired artifacts:
  `cline-tasks/agent-runtime-package-simplification-analysis.md` — supporting
  local analysis that this handoff summarizes for upstream implementation

## Current Status

- Done: reviewed the current external runtime-package reference, current
  `dynamic-agent-runner` spec/plan/tasks, prior Codex/Cline/OpenAI Agents SDK
  evaluations, and key runtime modules.
- Done: created
  `cline-tasks/agent-runtime-package-simplification-analysis.md` with a local
  design analysis and validation record.
- Done: this note packages the desired upstream changes as a separate feature
  request for the agent-development skill repo.
- Remaining: apply the requested changes in the upstream agent-development skill
  repo and validate the skill/reference there.

## Repository Context

- Current repo: `/Users/roschuma/Repos/roschuma/dynamic-agent-runner`
- Current branch at latest check: `develop`
- Branch status at latest check: working tree had a pre-existing modified
  `memory-bank/notes/historical-user-prompts.txt`, untracked local analysis
  artifact, and untracked `docs/`.
- Upstream target repo/path:
  `/Users/roschuma/Repos/roschuma/clinerules-roschuma/skills/agent-development-skill/`
- Upstream target file:
  `references/agent-runtime-package.md`

## Model Used

- The current interface does not expose the exact model name.

## Branch and Integration State

- Target branch: not checked in the upstream repo during this handoff.
- Relevant local artifacts:
  - `cline-tasks/agent-runtime-package-simplification-analysis.md`
  - `cline-tasks/agent-development-skill-runtime-package-feature-request.md`
- Relevant commits: none yet at handoff-note creation time.
- Planned integration method: manually apply or port the requested reference
  updates in the upstream `clinerules-roschuma` repository, then validate and
  commit there according to that repo's workflow.
- Backup branches: none created.

## Files Reviewed

- `/Users/roschuma/Repos/roschuma/clinerules-roschuma/skills/agent-development-skill/references/agent-runtime-package.md`
  — current upstream design reference to update.
- `specs/dynamic-agent-runner/spec.md` — current product/spec direction,
  including deferred OpenAI Agents SDK Python concepts and active constraints.
- `specs/dynamic-agent-runner/plan.md` — current technical plan and implemented
  E14/follow-up state.
- `specs/dynamic-agent-runner/tasks.md` — completed slices and deferred E9–E12 /
  OA1–OA10 backlog.
- `cline-tasks/codex-cli-evaluation.md` — Codex-derived lessons for tool
  exposure, MCP, policy, context, memory, and skills.
- `cline-tasks/cline-evaluation.md` — Cline-derived lessons for runtime layering,
  hooks, tool policy, compaction, MCP, and multi-agent delegation.
- `cline-tasks/codex-cline-combined-package-proposal.md` — consolidated accepted
  follow-up direction from Codex/Cline reviews.
- `cline-tasks/openai-agents-python-evaluation.md` — OpenAI Agents SDK Python
  evaluation and OA1–OA10 follow-up concepts.
- `cline-tasks/evaluation-follow-up-implementation-plan.md` — implemented
  follow-up plan, especially E14 async-first completion.
- `src/dynamic_agent_runner/models.py` — current manifest, node, tool, policy,
  behavior override, and workflow models.
- `src/dynamic_agent_runner/artifacts.py` — current artifact loading boundary.
- `src/dynamic_agent_runner/validation.py` — current validation of manifest,
  tool-index, and behavior overrides.
- `src/dynamic_agent_runner/executor.py` — current async-first executor and raw
  manifest-field usage points.
- `src/dynamic_agent_runner/registry.py` — current registry, exposure, policy,
  built-in tool pack, and tool-result boundaries.
- `src/dynamic_agent_runner/context.py` — current execution context boundary.
- `src/dynamic_agent_runner/api.py` — current sync/async public APIs.
- `src/dynamic_agent_runner/behavior.py` — current effective prompt/skill
  override derivation pattern.

## Files Changed

- `cline-tasks/agent-runtime-package-simplification-analysis.md` — local analysis
  artifact identifying simplification opportunities and tradeoffs.
- `cline-tasks/agent-development-skill-runtime-package-feature-request.md` — this
  feature-request handoff note.

## Untouched Areas and Unrelated Local Changes

- Intentionally not touched: upstream
  `/Users/roschuma/Repos/roschuma/clinerules-roschuma/...` files; this handoff
  only captures requested changes for later upstream work.
- Unrelated local changes at latest status check:
  - `memory-bank/notes/historical-user-prompts.txt` modified before this note.
  - `docs/` untracked before this note.
- Keep those unrelated changes out of any commit for this feature-request handoff
  unless the user explicitly scopes them in.

## Key Findings and Decisions

- Keep the current core runtime package idea: `agent-runtime.yaml` is the
  portable source of truth, `agent-graph.mmd` is derived, and primitive node kinds
  stay limited to `llm_step`, `tool_use_step`, and `decision_step` for
  `format_version: 1`.
- Simplify by organizing optional complexity, not by removing the artifact
  package boundary.
- The current upstream reference has too many optional top-level metadata fields
  in one flat namespace. This makes future capabilities look like peer concerns
  of `nodes`, `edges`, `tools`, and `skills`.
- Preferred upstream design change: classify manifest content into:
  - core executable fields
  - runtime policy fields
  - capability declarations
  - design metadata
- Preferred generated-manifest shape for new packages:

  ```yaml
  format_version: 1
  package_type: dynamic_agent_design
  package_id: <id>
  name: <optional>
  description: <optional>
  entrypoint: <node id>
  packaging: <package packaging>
  nodes: []
  edges: []
  tools: []
  skills: []
  output_contracts: {}
  runtime: {}
  metadata: {}
  extensions: {}
  ```

- `runtime` should hold executable policies the runner can interpret.
- `metadata` should hold design-only metadata such as patterns, phases, modes,
  roles, and participant groups.
- `extensions` should hold optional capability declarations such as context
  management, guardrails, MCP, approvals, sessions, and sandbox/workspace.
- Backward compatibility should be preserved: older flat fields can remain valid
  in `format_version: 1`, but newly generated packages should prefer the grouped
  shape.
- The upstream reference should warn clearly that optional metadata is not an
  enforcement guarantee unless a runner module explicitly supports it.
- The upstream reference should recommend that runners build a derived internal
  execution view such as `ExecutionPlan` / `PreparedNode` before adding optional
  features.

## Requested Upstream Feature Changes

1. Add a new section named **Core vs extension manifest contract**.
2. Replace or demote the flat “Additional optional metadata fields” list with
   grouped extension categories.
3. Add a field-classification table with these categories:
   - core executable
   - runtime policy
   - capability declaration
   - design metadata
4. Add the recommended grouped manifest shape using root `runtime`, `metadata`,
   and `extensions` maps.
5. Document compatibility guidance:
   - existing flat optional fields remain acceptable for `format_version: 1`
   - new generated packages should prefer grouped fields
   - consumers should preserve unknown fields when practical
6. Document extension validation behavior:
   - unsupported extension with `required: true` should fail closed
   - unsupported extension with `required: false` should be preserved and reported
   - supported extension with invalid shape should fail closed
7. Add runner-facing implementation guidance to build a derived `ExecutionPlan`
   / `PreparedNode` before adding more optional features.
8. Add `PreparedModelInput` / `prepare_model_input(...)` as the recommended seam
   for context preparation, token budgeting, prompt-cache observation, session
   pruning, compaction, and hierarchical prompt injection.
9. Add `ToolOrigin` / `ToolSource` as the recommended provenance object for
   registered, built-in, manifest, tool-index, override, MCP, and agent-as-tool
   sources.
10. Keep approval, sandbox, network, and mutation policy as separate nested
    dimensions for future write/command tools instead of expanding one flat
    `ToolPolicy` indefinitely.
11. Keep `RunOutcome` / `StepOutcome` style agent-loop semantics deferred until
    a future spec explicitly selects iterative agent execution.

## Suggested Upstream Patch Shape

Use the existing `agent-runtime-package.md` reference and modify it in-place.
Suggested high-level section flow:

1. Keep `## Purpose` and `## Artifact set and packaging` mostly unchanged.
2. In `## Runtime manifest sections`, keep required root fields, then introduce
   the grouped root model:
   - core root fields
   - `runtime`
   - `metadata`
   - `extensions`
3. Move the current optional design metadata into `metadata` examples.
4. Move capability-specific future concerns into `extensions` examples.
5. Keep `## Versioning and compatibility`, but add backward-compatible migration
   wording for flat optional fields.
6. Add a new runner-facing subsection near validation or node guidance:
   **Derived execution views for consumers**.

Suggested concise classification to add upstream:

- **Core executable** — required to traverse and execute; examples: `nodes`,
  `edges`, `entrypoint`; runtime should validate and enforce.
- **Runtime policy** — supported policy knobs; examples: `max_steps`,
  `retry_policy`, `token_budget`, `prompt_cache`; runtime should validate and
  enforce where implemented.
- **Capability declaration** — opt-in future/optional modules; examples: `mcp`,
  `sessions`, `sandbox`, `guardrails`; runtime should validate if the module is
  enabled, otherwise preserve and report.
- **Design metadata** — reader/planner metadata; examples: `patterns_present`,
  `phases`, `roles`; runtime should preserve and expose but not enforce by
  default.

## Validation Performed

- `git branch --show-current && git status --short` — pass; branch `develop`,
  with pre-existing modified `memory-bank/notes/historical-user-prompts.txt`,
  untracked `cline-tasks/agent-runtime-package-simplification-analysis.md`, and
  untracked `docs/` before this note was created.
- Source review listed in `## Files Reviewed` — pass.
- Handoff note validation before commit:
  `git diff --check -- <this file>` and `pre-commit run --files <this file>`
  — pass after line wrapping and EOF newline fixes.

## Open Questions or Risks

- The upstream repo branch/status was not inspected during this handoff; a future
  session should check it before editing upstream files.
- Exact wording and placement in upstream `agent-runtime-package.md` should be
  adjusted after reading the latest upstream copy in that repository.
- If the upstream skill reference has changed since this local analysis, reconcile
  this handoff against the current file before patching.
- This handoff intentionally does not update the local `dynamic-agent-runner`
  specs/tasks; those changes should be separately scoped if desired.

## Next Steps

- [ ] Open the upstream `clinerules-roschuma` repository.
- [ ] Check upstream branch and working tree status.
- [ ] Read the latest
      `skills/agent-development-skill/references/agent-runtime-package.md`.
- [ ] Apply the requested feature-reference changes from this handoff.
- [ ] Run upstream markdown validation or pre-commit on changed upstream files.
- [ ] Commit the upstream feature-reference update with a conventional commit
      message if requested.
- [ ] Optionally return to `dynamic-agent-runner` and add a small
      simplification-prerequisite backlog section to `specs/dynamic-agent-runner/tasks.md`.

## Resume Prompt

Continue from this handoff in the agent-development skill repository. First check
upstream repository branch and working tree status, then read the latest
`skills/agent-development-skill/references/agent-runtime-package.md`. Use this
handoff as the feature-request summary and use
`/Users/roschuma/Repos/roschuma/dynamic-agent-runner/cline-tasks/agent-runtime-package-simplification-analysis.md`
as supporting evidence. Update the upstream runtime-package reference to group
manifest complexity into core executable fields, runtime policy, design metadata,
and extension capability declarations. Preserve backward compatibility for
`format_version: 1` and avoid adding new primitive node kinds or enforcement
claims for unsupported optional metadata.
