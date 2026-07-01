# Graphify Semantic Extractor Tool Specification

## Metadata

- Feature slug: `graphify-semantic-extractor-tool`
- Mode: `guided`
- Artifact type: future feature specification
- Status: first-release implementation complete; endpoint and stock Graphify
  orchestration remain deferred; blended chunk planning is a follow-on
  sub-feature
- Related specs:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/subagent-tool-pack/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/llm-step-interpreter-middleware/spec.md`
  - `specs/rag-orchestration-contract/spec.md`
  - `specs/live-guardrail-execution/spec.md`
  - `specs/approval-interruption-resume/spec.md`
  - `specs/hash-chained-governance-audit/spec.md`
- Collateral:
  - `specs/graphify-semantic-extractor-tool/analysis.md`

## Objective

Add a package-owned Graphify extraction tool and console entrypoint that use
DAR's LLM interface and bounded parallel workflow capabilities to produce
Graphify-compatible semantic extraction artifacts from a curated knowledge
corpus in this or another repository.

The tool is useful with Graphify, but it is not a Graphify fork and not a
general model endpoint. DAR owns the controlled parallel extraction stage;
Graphify remains responsible for graph construction, clustering, reports,
curation, diagnostics, query, and promotion.

## Problem Statement

The repository's curated Graphify corpus is document-heavy and includes
instruction-like files such as `AGENTS.md` and `AGENTS.local.md`. Direct
Graphify extraction through local Osaurus models exposed three practical
problems:

1. sandboxed Graphify cannot always connect to a loopback model gateway without
   explicit escalation;
2. smaller local models can hit context limits on required corpus files;
3. instruction-tuned local models can treat corpus contents as live operating
   instructions instead of untrusted extraction data.

Standing up an OpenAI-compatible endpoint around DAR would let Graphify call DAR
as a provider, but it would hide chunking, schema enforcement, retry behavior,
and prompt-injection resistance behind a generic chat facade. A stock-compatible
artifact producer is the cleaner first release.

## Design Position

The first release should build a package-owned tool implementation:

```text
graphify detect
→ DAR graphify_semantic_extract tool
→ staged Graphify semantic artifacts
→ Graphify build/cluster/report
→ graphify_artifacts.py curate/validate/promote
```

The tool produces the semantic extraction artifacts Graphify expects, rather
than pretending to be an OpenAI-compatible model server. It must write only to a
candidate output root and must not mutate the accepted `graphify-out/` snapshot.

## Proposed Public Shape

The package should expose a narrowly named helper and console entrypoint. Names
are fixed for implementation planning:

```python
from dynamic_agent_runner.tools.graphify import (
    GraphifySemanticExtractionPolicy,
    create_graphify_semantic_extractor_tool,
)
```

Conceptual callable contract:

```text
graphify_semantic_extract(
    repo_root: str,
    corpus_manifest: object,
    output_dir: str,
    concurrency: int = 3,
    required_globs: list[str] | None = None,
    model_policy: object | None = None,
) -> GraphifySemanticExtractionResult
```

The model-visible tool remains the primary contract. The required
cross-repository script is a thin wrapper over the same package-owned
implementation:

```text
dynamic-agent-runner-graphify-extract \
  --repo-root PATH \
  --corpus-manifest PATH \
  --output-dir PATH \
  [--concurrency N] [--required-glob GLOB] [--model MODEL]
```

The script must invoke DAR's configured model adapter and bounded parallel
workflow; it must not shell out to additional Codex processes or implement a
second provider client.

## Package Boundary

The helper ships with the normal package install and remains opt-in at registry
construction time. Installing DAR does not expose the tool to workflows
automatically. Unit tests must not require live Graphify, Osaurus, OpenAI, local
models, or network access.

## Stock Graphify Integration

The tool must integrate by artifacts, not by provider emulation.

It should accept an admitted corpus manifest derived from Graphify detection
under the repository's `.graphifyignore` policy. It should emit:

- one immutable chunk manifest per extraction batch;
- one JSON result per chunk;
- a merged `.graphify_semantic_new.json`;
- a final `.graphify_semantic.json` candidate when validation passes;
- an audit file containing chunk ids, source file hashes, model/preset ids,
  retries, failures, and validation outcomes.

The tool must not write directly into accepted `graphify-out/`. A caller may
then run Graphify's normal merge/build/cluster/report flow and the repository's
existing `graphify_artifacts.py` curation and promotion gates.

## Functional Requirements

### FR-1: Stay Registry-Mediated and Script-Accessible

Given the package is installed, when no caller registers the Graphify semantic
extractor tool, then workflows must not see or invoke it.

Given another repository installs DAR, when it invokes
`dynamic-agent-runner-graphify-extract`, then the script must route through the
same package-owned extraction API and DAR model/worker policy.

### FR-2: Respect Curated Corpus Boundaries

Given a corpus manifest is supplied, when extraction starts, then every source
path must be relative to the declared repository root, resolve inside that root,
and be admitted by the caller-provided detection or policy evidence.

The tool must reject source code files, generated graph output, symlink escapes,
absolute paths, traversal paths, and files outside the declared corpus.

### FR-3: Treat Corpus Contents as Untrusted Data

Given a corpus file contains instructions such as `AGENTS.md`, when a worker
extracts facts, then the worker prompt and validation layer must treat the file
contents as data only.

The worker must not obey repository instructions, shell snippets, model
directions, tool-use requests, or policy text found inside corpus contents.

### FR-4: Produce Graphify-Compatible Semantic JSON

Given a worker completes a chunk, when it returns output, then the output must
be strict JSON matching Graphify's semantic extraction shape:

- `nodes`
- `edges`
- `hyperedges`
- token or usage metadata when available

Every accepted node, edge, and hyperedge must carry enough source provenance for
Graphify curation and later citation checks.

### FR-5: Run Bounded Parallel Extraction

Given a corpus has many files, when extraction runs, then the tool must split
work into deterministic chunks and execute workers through a bounded parallel
workflow.

The first release may default to the current in-process subagent concurrency
available to DAR. Higher concurrency such as ten-at-a-time must require an
explicit worker-pool design with per-worker output directories and no shared
writes to the same chunk file.

### FR-6: Validate Before Merge

Given a worker returns JSON, when the parent considers the chunk, then it must
validate schema, source paths, endpoint references, confidence values,
self-loops, duplicate edges, required metadata, and required-file coverage
before merging.

Invalid chunk output must be rejected, repaired through a bounded retry, or
marked failed. It must not be silently merged.

### FR-7: Preserve Deterministic Merge and Audit

Given multiple chunk workers complete in arbitrary order, when merge occurs,
then the merged semantic artifact must have deterministic ordering based on
chunk id and stable entity ids.

The audit must record successful, failed, retried, skipped, and repaired chunks
without requiring raw child transcripts in the accepted graph.

### FR-8: Use DAR Runtime Policy

Given the tool calls models or child workers, when execution runs, then it must
use DAR-owned model adapters, budget policy, tracing, approval boundaries,
guardrails, and result shaping where those behaviors apply.

The tool must not bypass the registry or call model providers through ad hoc
client code hidden from DAR traces.

### FR-9: Keep OpenAI-Compatible Endpoint Emulation Deferred

Given Graphify can call OpenAI-compatible providers, when this feature is
implemented, then it must not require standing up a DAR OpenAI-compatible
endpoint.

A future endpoint adapter may be specified later if a caller needs transparent
Graphify provider emulation. That future adapter must preserve schema
enforcement, chunk audit, and prompt-injection resistance.

### FR-10: Support Blended Token- and File-Bounded Chunking (Follow-On)

The post-first-release extractor should replace the current fixed file-count
chunking policy with a bounded hybrid policy:

- pack admitted documents by an estimated input-token budget, grouped by
  parent directory so related artifacts remain together;
- enforce a maximum file count per chunk as a safety bound for very small
  documents;
- cap the amount of content read from an individual document so one large file
  cannot consume the whole request;
- split and retry a chunk when the provider reports context overflow, output
  truncation, or a validation failure attributable to request density;
- preserve deterministic chunk ids, source hashes, audit records, and the
  existing DAR approval, tracing, validation, and result-shaping boundaries.

The initial blended defaults should be configurable rather than hard-coded into
the public contract. A candidate starting profile is a 40,000-token input
budget, a 20--25 file maximum, and a 20,000-character per-file cap; benchmark
results must determine the released defaults.

To improve cross-chunk accuracy without resending source text, a later slice
may add a reconciliation pass over compact node and relationship summaries.
That pass must not mutate accepted Graphify output and must use the same DAR
model and approval path as primary extraction.

This sub-feature is not part of the first-release acceptance gate. Until it is
implemented, the first-release fixed chunk policy remains the source of truth.

## Non-Goals

This feature does not:

- replace Graphify;
- mutate accepted `graphify-out/` directly;
- install or manage Osaurus;
- require OpenAI, Gemini, or another remote provider;
- add an unbounded agent farm;
- spin up additional Codex CLI processes to multiply subagent limits;
- expose raw child transcripts as graph provenance;
- create a general OpenAI-compatible model server;
- make Graphify a runtime dependency of the base package;
- provide a second model-provider client inside the script;
- shell out to additional Codex CLI processes for parallelism;
- authorize implementation without a separate TDD task slice.
- change the first-release fixed chunk policy implicitly; blended chunking is a
  separately scheduled follow-on slice.

## First Release Boundary

The initial implementation slice should include:

1. A fake-testable Graphify semantic extractor tool helper.
2. Deterministic corpus manifest validation.
3. Deterministic chunk planning.
4. A fake worker/LLM path for unit tests.
5. Strict JSON chunk validation.
6. Deterministic merge to staged semantic artifacts.
7. Audit output with chunk status and source hashes.
8. The `dynamic-agent-runner-graphify-extract` console entrypoint with
   `--help`, manifest, output, concurrency, required-glob, and model-policy
   options.
9. Documentation showing how a caller can hand staged artifacts to Graphify.

The first release may use serial or low-concurrency execution if that is the
smallest testable slice. Ten-at-a-time execution is deferred until the worker
pool has explicit locking, output isolation, retry accounting, and process
cleanup.

Blended token/file chunking and cross-chunk reconciliation are explicitly
post-first-release work. They require focused benchmarks and TDD coverage
before changing the default chunk behavior.

## Acceptance Criteria

- Given the tool is not registered, no workflow sees it.
- Given another repository invokes the console script with a valid manifest, the
  script calls the package-owned extraction path and writes staged artifacts
  without requiring that repository to import DAR internals.
- Given a manifest includes a source outside the repo root, extraction fails
  before any worker runs.
- Given a manifest includes code files or generated `graphify-out` content,
  extraction fails before any worker runs.
- Given a corpus file contains "ignore previous instructions" or equivalent
  text, worker instructions treat it as data and output extraction JSON only.
- Given one worker returns invalid JSON, the parent rejects or retries that
  chunk and records the outcome in the audit.
- Given workers finish out of order, the merged semantic artifact is stable
  across repeated runs with the same chunk results.
- Given required globs are supplied, missing required coverage fails validation.
- Given a successful run, staged artifacts are written outside accepted
  `graphify-out/`.
- Given unit tests run, they use fake workers/model adapters and do not call
  live Graphify, Osaurus, OpenAI, local models, shell, network, or external
  files outside test fixtures.

## TDD Implementation Notes

Implementation must follow TDD per repository policy:

1. RED: public helper, registry factory, and console `--help` contract.
2. RED: manifest path containment and corpus rejection tests.
3. RED: chunk-planning determinism tests.
4. RED: invalid JSON and prompt-injection fixture tests.
5. RED: deterministic merge and audit tests.
6. RED: CLI-to-package delegation with an injected fake worker/model path.
7. GREEN: minimal fake-worker implementation and console wrapper.
8. REFACTOR: only after the tests pass and the public surface remains narrow.

## Implementation Preparation Decisions

- Graphify remains an external executable and is not a package dependency. The
  first release produces the semantic artifacts consumed by Graphify's stock
  workflow.
- DAR accepts a small package-owned corpus-manifest contract. A caller or thin
  integration adapter may derive it from Graphify detect output; the extractor
  does not parse or invoke the Graphify CLI itself.
- The first release exposes a Python API, registry tool, and the
  `dynamic-agent-runner-graphify-extract` console entrypoint. The script is a
  thin cross-repository wrapper over the same API.
- Validation targets the stable Graphify semantic subset (`nodes`, `edges`, and
  `hyperedges` with provenance and confidence fields) using checked-in JSON
  fixtures rather than a Graphify runtime dependency.
- The implementation uses the package's existing dependencies and standard
  library; it adds no Graphify-specific or schema-validation dependency.
