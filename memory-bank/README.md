# Memory Bank

This directory stores durable project context for future Cline sessions working
on `dynamic-agent-runner`.

The memory bank is background project memory. It is not a replacement for:

- task-specific handoff notes under `cline-tasks/` when branch, validation, or
  commit-boundary state must be preserved
- source files, tests, or configuration as the authoritative implementation
  record
- external issue trackers or design documents when those are the source of
  truth for product requirements

## Core Files

- `projectbrief.md` — project purpose, scope, and constraints
- `productContext.md` — user and product context
- `systemPatterns.md` — observed architecture and repository patterns
- `techContext.md` — tooling, dependencies, and environment setup
- `activeContext.md` — current focus and near-term next steps
- `progress.md` — what exists, what is in flight, and remaining work

## Repository-specific Conventions

- Keep entries concise and grounded in observed repository state.
- Do not invent implementation details while the repository is still sparse.
- Update `activeContext.md` and `progress.md` after meaningful milestones.
- Add supporting notes under `memory-bank/notes/` only when they capture durable
  decisions, risks, or domain context that would clutter the core files.
- Treat `memory-bank/notes/historical-user-prompts.txt` as a durable
  prompt-history note. Append only substantive user prompts that are not already
  represented elsewhere in the note.
- `memory-bank/` is the project-local memory location. Use Obsidian memory only
  when the user explicitly requests an Obsidian-vault workflow.
- Keep prompt-history entries verbatim enough to preserve diagnostic context,
  especially error snippets that drove feature work.
