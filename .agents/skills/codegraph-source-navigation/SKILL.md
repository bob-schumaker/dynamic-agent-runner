---
name: codegraph-source-navigation
description: Use in this repository for indexed source discovery, focused code reading, call-path tracing, and pre-edit source context with CodeGraph when a .codegraph index exists.
compatibility: Requires a CodeGraph CLI or MCP installation and a repository-local .codegraph index.
related_rules:
  - AGENTS.local.md
---

# Dynamic Agent Runner CodeGraph source navigation

This active paired-execution skill implements the CodeGraph mechanics governed
by `AGENTS.local.md`. It is for current source structure, not documentation,
organizational knowledge, Git history, or correctness validation.

## Resolve the CLI

Prefer the global executable, then the repository fallback:

```bash
if command -v codegraph >/dev/null 2>&1; then
    CODEGRAPH=codegraph
elif [ -x .agent-tools/bin/codegraph ]; then
    CODEGRAPH=.agent-tools/bin/codegraph
else
    echo "CodeGraph is not installed" >&2
    exit 1
fi
```

Stop using CodeGraph for the task when `.codegraph/codegraph.db` is absent. Do
not initialize it implicitly.

## Query sequence

1. Run `$CODEGRAPH status` when freshness is uncertain.
2. Use the `codegraph_explore` MCP tool when available; otherwise run:

   ```bash
   "$CODEGRAPH" explore "<question, file, or symbol names>"
   ```

3. Ask one narrower follow-up when the first result is insufficient. Use raw
   `rg` or file reads only for unsupported files, docs/configuration, or a detail
   the graph omitted.
4. Before editing, retain the returned callers and blast-radius evidence in the
   task context. CodeGraph does not replace tests or runtime verification.

Useful focused commands:

```bash
"$CODEGRAPH" query "<symbol>"
"$CODEGRAPH" impact "<symbol>" --depth 2
"$CODEGRAPH" status
"$CODEGRAPH" sync
```

Use `sync` only when status or the MCP response reports stale data and the
watcher is unavailable. Normal MCP sessions auto-sync.

## Boundaries

- Route process-level risk and working-tree diff impact to GitNexus.
- Route design rationale and code-to-doc relationships to Graphify.
- If CodeGraph reports no index, use normal source tools for the remainder of
  the task rather than repeating failed calls.

## Completion checks

- The index existed and the selected result named the relevant source.
- Stale-file warnings were handled explicitly.
- Any implementation claim was verified with the repository's tests or runtime.

Trigger examples: "where is this implemented", "trace this call", "read this
symbol", "what source should I edit". Negative triggers: Git blame/history,
meeting notes, or installing CodeGraph.
