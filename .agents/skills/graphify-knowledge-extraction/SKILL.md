---
name: graphify-knowledge-extraction
description: Use with the vendored Graphify skill in this repository to enforce its knowledge-only corpus, run semantic extraction through Osaurus with the approved OpenAI models, reject source-code graph leakage, and reduce inferred-edge noise.
compatibility: Requires Graphify, Osaurus, the repository's .graphifyignore allowlist, and a configured Osaurus OpenAI provider for the preferred cloud models.
related_rules:
  - AGENTS.local.md
---

# Dynamic Agent Runner Graphify addon

Use this active paired-execution addon after reading the vendored Graphify skill
and before running Graphify commands in this repository. `AGENTS.local.md` owns
tool-selection policy; this skill owns Graphify's local corpus and query
mechanics.

## Knowledge-only corpus

Graphify is restricted to the allowlist in `.graphifyignore`:

- root project instructions and Markdown documentation
- `docs/source/`
- `memory-bank/`
- `cline-tasks/`

CodeGraph owns source structure and call navigation. GitNexus owns execution
flows and change impact. Do not use Graphify to index `src/`, `tests/`, `bin/`,
scripts, package internals, or generated/build output.

Before a full extraction, verify the restriction:

```bash
if command -v graphify >/dev/null 2>&1; then
    GRAPHIFY="$(command -v graphify)"
else
    GRAPHIFY=".agent-tools/bin/graphify"
fi
python="$(head -1 "$GRAPHIFY" | sed 's/^#!//; s/ -E$//')"
"$python" - <<'PY'
from pathlib import Path
from graphify.detect import detect

result = detect(Path("."))
code = result.get("files", {}).get("code", [])
if code:
    raise SystemExit(f"Graphify knowledge scope leaked {len(code)} code files")
print(f"Graphify knowledge corpus: {result['total_files']} files")
PY
```

If code files are reported, stop and fix `.graphifyignore`; do not extract.

## Osaurus semantic extraction

Osaurus is the only provider gateway for Graphify semantic extraction and
community labeling in this repository. Do not call OpenAI directly and do not
substitute Codex subagents for semantic chunks.

### Approved model order

Use this order:

1. `openai-chatgpt/gpt-5.4-mini` — default for extraction and labeling; it
   passed the Graphify schema gate consistently and was materially faster than
   the other acceptable model.
2. `openai-chatgpt/gpt-5.5` — quality fallback only when Mini fails schema or
   semantic review; expect higher latency.
3. `qwen3.6-27b-mxfp4` — local contingency only when cloud processing is not
   authorized or unavailable. Run a schema probe first and do not merge output
   that needs more than the one permitted correction retry.

Do not use these models for production Graphify extraction unless a new
benchmark shows they pass the current schema and corpus gates:

- `foundation`
- `laguna-xs.2-jangtq`
- `gemma-4-26b-a4b-it-jang_4m`
- `gemma-4-31b-it-qat-mxfp4`

With the Osaurus ChatGPT/Codex sign-in, `gpt-5.4-nano` and `gpt-5.3-codex` are
advertised but rejected by the provider. Do not select them as fallbacks.

### Authentication and provider configuration

Configure the OpenAI ChatGPT provider through Osaurus Management → Providers
using its supported browser sign-in. Osaurus owns token storage and refresh.
Treat `~/.codex/auth.json` as a Codex-private password file: never inspect it for
Graphify, copy tokens from it, or expose it to Graphify or Osaurus.

For loopback OpenAI-compatible calls, `OPENAI_API_KEY=osaurus` is a non-secret
SDK placeholder. The real provider credentials remain inside Osaurus.

### Runtime checks and process hygiene

Before extraction, verify one runtime instance and discover models and agents:

```bash
pgrep -af '/Applications/Osaurus.app|Contents/MacOS/osaurus'
osaurus status
osaurus list
curl -fsS http://127.0.0.1:1337/v1/models
curl -fsS http://127.0.0.1:1337/agents
```

Exactly one Osaurus app process should be running. Do not use `open -n`; it
creates duplicate app instances. If Launch Services cannot find the executable,
launch `/Applications/Osaurus.app/Contents/MacOS/osaurus` directly once and
retain its process/session handle so it can be stopped after extraction.

Prefer a dedicated extraction agent whose effective model is the selected
model, with tools and memory disabled and temperature between `0.1` and `0.3`.
Osaurus does not currently expose agent creation through its public HTTP API.
If no suitable agent exists, use Graphify's native OpenAI-compatible backend
against Osaurus without `X-Osaurus-Agent-Id`; this provides no agent memory
injection and sends no tools.

### Native Graphify-to-Osaurus configuration

Use the selected model consistently for semantic extraction and community
labeling:

```bash
export OPENAI_API_KEY=osaurus
export OPENAI_BASE_URL=http://127.0.0.1:1337/v1
export OPENAI_MODEL=openai-chatgpt/gpt-5.4-mini
export GRAPHIFY_OPENAI_MODEL="$OPENAI_MODEL"

graphify extract . \
  --backend openai \
  --model "$OPENAI_MODEL" \
  --max-concurrency 4 \
  --token-budget 60000 \
  --api-timeout 600

graphify cluster-only . \
  --backend=openai \
  --model="$OPENAI_MODEL" \
  --max-concurrency=4 \
  --batch-size=100
```

The native path handles allowlisted documents and documentation images. Before
running it, state explicitly that the allowlisted corpus will be sent through
the configured OpenAI provider. Do not send source files or private vaults as
part of a repository Graphify pass.

For a dedicated agent path, send each semantic chunk's unchanged extraction
spec to `POST http://127.0.0.1:1337/agents/{id}/run`. Collect only the final
structured JSON, validate it, and retry malformed output once with a
schema-only correction prompt. Do not merge invalid output.

### Post-extraction scope and schema gates

Graphify detection reporting zero code files is necessary but not sufficient:
documentation can mention implementation paths that a model may incorrectly
emit as source-code nodes. Before accepting the graph:

- remove or reject every node with `file_type:"code"`
- remove or reject every `calls` edge
- require every node, edge, and hyperedge `source_file` to be inside the
  `.graphifyignore` allowlist
- remove edges and hyperedges that reference rejected or missing nodes
- require `EXTRACTED` confidence score `1.0`
- require INFERRED scores to be exactly one of `0.95`, `0.85`, `0.75`, `0.65`,
  or `0.55`; normalize continuous scores downward to the nearest allowed value
- require AMBIGUOUS scores between `0.1` and `0.3`
- rerun clustering and label any missing communities after filtering
- run `graphify diagnose multigraph --graph graphify-out/graph.json --json` and
  require zero dangling/missing endpoints, self-loops, duplicates, and collapsed
  edge pairs

Run a smoke query and verify every cited source is allowlisted. Treat
AMBIGUOUS report connections as investigation prompts, not established facts.

Use `osaurus list` to verify local contingency models rather than assuming a
folder name is registered. Model downloads require explicit user approval.

Never run `graphify update .`, `graphify watch`, or Graphify hook installation
in this repository. Those commands perform structural code maintenance.

If a query result cites `.py`, `.js`, `.ts`, or other source files, treat the
graph as legacy code collateral: stop using it and run
the bootstrap script from `knowledge-graph-bootstrap` with `--cleanup-only`,
then rebuild from the allowlisted knowledge corpus.

## Low-INFERRED analysis

Graphify currently has no built-in low-INFERRED mode. Avoid `--mode deep` when
lower inferred-edge volume matters.

For stricter analysis, create an extracted-only graph and query that graph with
`--graph`:

```bash
python - <<'PY'
import json
from pathlib import Path

p = Path("graphify-out/graph.json")
g = json.loads(p.read_text())
g["links"] = [
    e for e in g.get("links", [])
    if e.get("confidence") == "EXTRACTED"
]
Path("graphify-out/graph.extracted-only.json").write_text(json.dumps(g, indent=2))
PY

"$GRAPHIFY" query "..." --graph graphify-out/graph.extracted-only.json
```

## Narrowed knowledge-graph rebuilds

When replacing a legacy code graph with the knowledge-only graph, Graphify may
refuse to overwrite `graphify-out/graph.json` because the new graph is much
smaller. Remove the confirmed generated legacy output before extraction instead
of forcing an unexplained node-count reduction.

## Completion checks

- Detection reports zero code files.
- Every semantic chunk was routed through Osaurus with the selected approved
  model and passed the structured extraction-schema check.
- The final graph contains no `code` nodes, `calls` edges, out-of-scope sources,
  dangling hyperedge members, or invalid confidence scores.
- Query results cite only allowlisted knowledge sources.
- No Graphify watcher or hook is enabled.
- Semantic extraction, not AST-only update, refreshed changed knowledge.

Trigger examples: documentation rationale, decisions, specifications, or
cross-note relationships. Negative triggers: locating source, tracing calls,
blast-radius analysis, or working-tree impact.
