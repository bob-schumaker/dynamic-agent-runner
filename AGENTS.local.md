# AGENTS.local.md

<!-- rumdl-disable MD013 -->

Additional instructions for coding agents in this repo. Read this file before every task.

**Working code only. Finish the job. Plausibility is not correctness.**

This file follows the [AGENTS.md](https://agents.md) open standard (Linux Foundation / Agentic AI Foundation). Claude Code, Codex, Cursor, Windsurf, Copilot, Aider, Devin, Amp read it natively.

<!-- BEGIN MANAGED KNOWLEDGE-GRAPH ROUTING -->
<!-- rumdl-disable MD041 -->
## Knowledge-Graph Routing

Use the narrowest concern owner; do not invoke every graph mechanically.

| Need | First Choice | Boundary |
|---|---|---|
| Locate or read current source; trace exact calls | CodeGraph | Requires `.codegraph/`; otherwise use normal source tools |
| Connect documentation, decisions, plans, and rationale | Graphify | Requires a curated `.graphifyignore` and knowledge-only graph |
| Discover execution processes or assess change impact | GitNexus | Requires `.gitnexus/`; not a Git-history database |
| Commits, PRs, blame, authorship, or ownership history | Git and SCM tooling | Do not route to the graph trio |

For mixed questions, sequence Graphify for documented intent, CodeGraph for the
exact implementation, GitNexus for change risk, and Git/SCM for provenance.
Graph results are context evidence; tests, linters, and runtime behavior remain
correctness authority.

Load the corresponding installed skill before graph work:

- `codegraph-source-navigation`
- `graphify-knowledge-extraction`
- `gitnexus-change-impact`
- `knowledge-graph-bootstrap` for setup, repair, or instruction maintenance

Do not initialize or refresh indexes during ordinary questions. Graphify corpus
changes require reviewed, project-specific `.graphifyignore` curation. Refresh
Graphify through the staged curation, validation, diagnostics, and snapshot
promotion procedure in `graphify-knowledge-extraction`; preserve the accepted
snapshot whenever any candidate gate fails.
<!-- END MANAGED KNOWLEDGE-GRAPH ROUTING -->

<!-- BEGIN MANAGED MEMORY-BANK ROUTING -->
<!-- rumdl-disable MD041 -->
For "initialize memory bank", "update memory bank", or "update memory-bank", use
`memory-bank-maintenance`.
Use `memory-bank/` as project-local memory.
Use `obsidian-memory` only for explicit Obsidian-vault memory.
Do not treat Obsidian memory as current project memory unless explicitly asked.
<!-- END MANAGED MEMORY-BANK ROUTING -->

<!-- BEGIN MANAGED PROJECT OBSIDIAN WIKI GUIDANCE -->
<!-- rumdl-disable MD041 -->
Before answering from or changing the repo-local generated wiki, read its `index.md` first and then only task-relevant linked pages.
Keep raw sources outside the repo-local generated wiki immutable.
Codex owns generated wiki pages under the repo-local generated wiki.
Update its `index.md` and `log.md` for every wiki mutation.
Keep source summaries factual and put interpretation in concepts or synthesis pages.
Use `type:`, `tags:`, and `date_updated:` frontmatter on generated pages.
Use the global Obsidian skills only for live source discovery and read-only source-vault checks.
<!-- END MANAGED PROJECT OBSIDIAN WIKI GUIDANCE -->
