---
name: gitnexus-change-impact
description: Use in this repository for GitNexus execution-flow discovery, symbol blast-radius analysis, and working-tree change-impact checks before edits or commits when a .gitnexus index exists.
compatibility: Requires a GitNexus CLI or MCP installation, Git, and a repository-local .gitnexus index.
related_rules:
  - AGENTS.local.md
---

# Dynamic Agent Runner GitNexus change impact

This active paired-execution skill implements the GitNexus mechanics governed by
`AGENTS.local.md`. Current GitNexus analyzes code structure, execution processes,
and Git diffs. It does not model commit/PR history, contributors, or ownership.

## Resolve the CLI

```bash
if command -v gitnexus >/dev/null 2>&1; then
    GITNEXUS=gitnexus
elif [ -x .agent-tools/bin/gitnexus ]; then
    GITNEXUS=.agent-tools/bin/gitnexus
else
    echo "GitNexus is not installed" >&2
    exit 1
fi
```

Run `$GITNEXUS status` first. If `.gitnexus/` is absent or status fails because
the repository is not indexed, use CodeGraph or normal source tools and do not
run `analyze` implicitly.

## Required safety gates

Before editing a function, class, or method:

```bash
"$GITNEXUS" impact "<symbol>"
```

Report direct callers, affected processes, and the returned risk level. Warn the
user before editing when the result is HIGH or CRITICAL. Disambiguate shared
names with `--file`, `--uid`, or `--kind` as suggested by the CLI.

Before committing:

```bash
"$GITNEXUS" detect-changes
```

Confirm the affected symbols and processes match the intended diff. This is an
impact check, not a substitute for tests, lint, or review.

## Exploration commands

```bash
"$GITNEXUS" query "<concept or process>"
"$GITNEXUS" context "<symbol>"
"$GITNEXUS" impact "<symbol>"
```

Use `query` for process-grouped discovery and `context` for a 360-degree symbol
view. Prefer CodeGraph when the main need is verbatim, line-numbered source.

## Maintenance

After a commit or branch change, or when status reports staleness, run:

```bash
"$GITNEXUS" analyze --skip-agents-md --skip-skills
```

Keep the same `--skip-agents-md --skip-skills` protections on ordinary
`analyze` runs. Never allow generated context to replace `AGENTS.local.md`.

## Completion checks

- Impact ran before symbol edits.
- HIGH/CRITICAL risk was surfaced before editing.
- `detect-changes` ran before commit preparation.
- Tests and linters independently verified behavior.

Trigger examples: "what breaks if I change this", "which flows are affected",
"check this diff's impact". Negative triggers: commit authorship/blame, reading
verbatim source, or installing GitNexus.
