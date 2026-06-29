# AGENTS.local.md

<!-- rumdl-disable MD013 -->

Additional instructions for coding agents in this repo. Read this file before every task.

**Working code only. Finish the job. Plausibility is not correctness.**

This file follows the [AGENTS.md](https://agents.md) open standard (Linux Foundation / Agentic AI Foundation). Claude Code, Codex, Cursor, Windsurf, Copilot, Aider, Devin, Amp read it natively.

## 1. Knowledge-graph routing

This repository can expose three complementary local graphs. Use the narrowest
one that matches the question; do not call all three mechanically.

| Need | First choice | Why |
|---|---|---|
| Locate or read current source, trace calls, inspect a named symbol | CodeGraph | Returns focused, line-numbered source and call paths |
| Assess blast radius, execution processes, or working-tree change impact | GitNexus | Models processes and maps diffs to affected symbols and flows |
| Connect documentation, specifications, decisions, and project knowledge | Graphify | Builds a semantic graph from the allowlisted knowledge corpus |

GitNexus is not a commit-, pull-request-, contributor-, or ownership-history
database. Use Git history tools for those questions.

Availability is per repository:

- Use CodeGraph only when `.codegraph/codegraph.db` exists. Otherwise use normal
  source tools and mention the `knowledge-graph-bootstrap` skill if indexing
  would materially help.
- Use GitNexus only when `.gitnexus/` exists and `gitnexus status` succeeds.
- Use Graphify only when `graphify-out/graph.json` exists and was built from the
  `.graphifyignore`-restricted knowledge corpus.
- Resolve a missing global executable through `.agent-tools/bin/<tool>` before
  treating an installed graph as unavailable.

For mixed questions, sequence the tools by evidence: Graphify for documented
intent, CodeGraph for the exact implementation, and GitNexus for change risk.
Do not use one tool as a fallback for another tool's area of concern. Verify all
claims against tests, linters, or runtime behavior; graph results are navigation
and impact evidence, not correctness proof.

## 2. Using CodeGraph

Read `.agents/skills/codegraph-source-navigation/SKILL.md` before CodeGraph work.

- Prefer `codegraph_explore` when the MCP tool is available. Otherwise run
  `codegraph explore "<question or symbols>"`.
- Use CodeGraph before grep/find or broad file reads for indexed source. Use raw
  tools for docs, configuration, unsupported files, or a specific detail absent
  from the result.
- Treat a staleness banner as authoritative. Read only the named pending files,
  or run `codegraph status` and `codegraph sync` when the watcher is unavailable.
- Do not initialize CodeGraph during an ordinary task. Index creation is an
  explicit bootstrap/maintenance action.
- Do not use CodeGraph for specifications, decisions, meeting notes, or other
  prose knowledge.

## 3. Using GitNexus

Read `.agents/skills/gitnexus-change-impact/SKILL.md` before GitNexus work.

- Before editing a function, class, or method in an indexed repository, run
  `gitnexus impact <symbol>` and report HIGH or CRITICAL risk before proceeding.
- Use `gitnexus query` for process-oriented discovery and `gitnexus context` for
  a named symbol's callers, callees, and process participation.
- Before committing, run `gitnexus detect-changes` and confirm the affected
  symbols and execution flows match the intended diff.
- Refresh the index with `gitnexus analyze --skip-agents-md --skip-skills` after
  commits, branch changes, or when `gitnexus status` reports staleness. Do not
  let generated GitNexus context replace this file or the repo-local skills.
- Do not use GitNexus as a verbatim source reader, documentation graph, or Git
  history database.

## 4. Using Graphify

Read the vendored Graphify skill and then
`.agents/skills/graphify-knowledge-extraction/SKILL.md` before Graphify work. The
repo-local knowledge-only scope overrides the vendored skill's broader code
capabilities for this repository.

- For cross-source or rationale questions, first run
  `graphify query "<question>"`. Use `graphify path "<A>" "<B>"` for
  relationships and `graphify explain "<concept>"` for focused concepts.
- If `graphify-out/wiki/index.md` exists, use it for broad navigation. Read
  `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when the
  focused commands do not surface enough context.
- Never use `graphify update .`, `graphify watch`, or Graphify Git/Codex hooks in
  this repository; those paths rebuild source-code structure owned by CodeGraph.
- Refresh Graphify only after knowledge-corpus changes, using a full semantic
  extraction that respects `.graphifyignore`. Code changes alone do not require
  a Graphify refresh.
- Route Graphify semantic extraction and community labeling through Osaurus.
  The default model is `openai-chatgpt/gpt-5.4-mini`; use
  `openai-chatgpt/gpt-5.5` only when Mini fails a schema or semantic-quality
  gate. Do not bypass Osaurus to call OpenAI directly.
- Keep OpenAI authentication inside Osaurus's configured provider. Never read,
  copy, or adapt `~/.codex/auth.json` for Graphify or another third-party tool.
- Before extraction, require a healthy single Osaurus server and verify that
  the selected model appears in `http://127.0.0.1:1337/v1/models`. Follow the
  paired Graphify skill for provider configuration, agent/direct-endpoint
  selection, model fallbacks, process hygiene, and structured-output gates.

## 5. Bootstrap and maintenance

Read `.agents/skills/knowledge-graph-bootstrap/SKILL.md` before installing,
configuring, repairing, or re-indexing this toolchain. The supported entry point
is `.agents/skills/knowledge-graph-bootstrap/scripts/bootstrap-knowledge-graphs.sh`;
use `--dry-run` before a real run.
