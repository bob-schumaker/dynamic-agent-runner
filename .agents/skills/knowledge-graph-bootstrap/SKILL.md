---
name: knowledge-graph-bootstrap
description: Use when installing, configuring, checking, repairing, or initializing the repository's CodeGraph, GitNexus, and Graphify toolchain with global-first and repository-local fallback behavior.
compatibility: Requires macOS or Linux, Bash, curl, Git, and either uv/Python or npm/Node depending on the tool being installed; network access is required for installation.
related_rules:
  - AGENTS.local.md
---

# Knowledge-graph toolchain bootstrap

This active paired-execution skill owns installation and index-maintenance
mechanics. `AGENTS.local.md` owns tool-selection policy.

## Entry point

From the repository root, preview before applying:

```bash
BOOTSTRAP=.agents/skills/knowledge-graph-bootstrap/scripts/bootstrap-knowledge-graphs.sh
"$BOOTSTRAP" --dry-run
"$BOOTSTRAP"
```

The default `auto` scope tries user-global installation first and falls back to
`.agent-tools/` in this repository independently for each tool. Alternatives:

```bash
"$BOOTSTRAP" --scope global
"$BOOTSTRAP" --scope repo
"$BOOTSTRAP" --skip-agent-config
"$BOOTSTRAP" --skip-index
"$BOOTSTRAP" --cleanup-only
```

Global configuration targets Codex because this repository's durable routing is
in `AGENTS.local.md`. Repository-local CLI fallbacks remain usable without MCP.

## Expected installation model

- CodeGraph: prefer its self-contained release bundle so the host Node version
  cannot violate CodeGraph's supported `<25` runtime range.
- GitNexus: install the npm CLI globally, or under
  `.agent-tools/gitnexus/` when global npm installation fails.
- Graphify: prefer `uv tool install graphifyy`, fall back to a user-level pip
  install, or create an isolated local environment under `.agent-tools/graphify/`.

The bootstrap must not rewrite `AGENTS.local.md`. GitNexus indexing uses
`--skip-agents-md --skip-skills`. Graphify knowledge extraction requires a
`.graphifyignore` allowlist and must never run its AST-only `update` path here.

Before installation or indexing, the bootstrap inspects existing root and
`src/` Graphify graphs. A graph is legacy code collateral when a node declares
`file_type`/`type` as `code` or its provenance names a source-code extension.
Only after that evidence is present, cleanup:

- removes `graphify-out/` and `src/graphify-out/`
- removes Graphify entries from `.codex/hooks.json`, preserving other entries
- removes only Graphify-marked blocks from Git `post-commit` and
  `post-checkout` hooks

Knowledge-only graphs are preserved. Unreadable or invalid graphs are reported
and preserved because they cannot be classified safely. Use `--cleanup-only`
to run this gate without installing or indexing tools.

## Index expectations

After a successful run, verify:

```bash
codegraph status || .agent-tools/bin/codegraph status
gitnexus status || .agent-tools/bin/gitnexus status
```

The bootstrap does not create a structural Graphify code graph. Set
`GRAPHIFY_BOOTSTRAP_BACKEND` to run a knowledge-only semantic extraction during
bootstrap, or run the full `/graphify .` workflow later. Without either, a
missing `graphify-out/graph.json` is expected and Graphify remains unavailable.
When a Graphify graph was built, run the zero-code corpus check in
`graphify-knowledge-extraction` before treating it as available.

## Safety and failure behavior

- Installation is a networked mutation; run only when explicitly requested.
- Use `--scope repo` when global config or package locations must not change.
- A failure in `auto` scope falls back per tool. A failure in `global` or `repo`
  scope stops and reports the failing tool.
- Do not delete CodeGraph, GitNexus, or knowledge-only Graphify indexes as part
  of repair. The sole automatic deletion is an evidence-confirmed legacy
  Graphify code graph.

Trigger examples: "install the graph tools", "bootstrap CodeGraph, GitNexus,
and Graphify", "repair the indexes". Negative triggers: ordinary codebase
questions or routine implementation work.
