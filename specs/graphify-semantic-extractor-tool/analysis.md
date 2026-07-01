# Graphify Semantic Extractor Tool Analysis

## Purpose

This collateral records the discussion and experiments that motivated
`specs/graphify-semantic-extractor-tool/spec.md`. It is design evidence, not
implementation authority.

## Starting Context

The repository is migrating knowledge-graph skills from repo-local copied skill
files under `.agents/skills/` to installed or vendored skill sources. During that
maintenance work, Graphify remained scoped to the curated knowledge corpus,
while CodeGraph owned source navigation and GitNexus owned change impact.

The accepted Graphify graph was intentionally left untouched unless a new
candidate passed staged extraction, curation, validation, diagnostics, and smoke
query gates.

## Corpus and Existing Graph Facts

Graphify detection under the current `.graphifyignore` policy found:

- 182 document files;
- about 265k words;
- zero code files;
- no skipped sensitive files in the inspected run.

The existing accepted `graphify-out/graph.json` remained healthy during the
experiments:

- 350 nodes;
- 411 edges;
- no dangling endpoints;
- no self-loops;
- no exact duplicate edges;
- no same-endpoint collapsed edge groups.

## Osaurus and Direct Graphify Extraction Findings

Direct Graphify semantic extraction through Osaurus was explored first because
it fits Graphify's stock `--backend openai` path.

Observed model inventory changed from the older notes. The live Osaurus model
surface included local models such as:

- `foundation`
- `gemma-4-26b-a4b-it-jang_4m`
- `gemma-4-31b-it-qat-mxfp4`
- `laguna-xs.2-jangtq`
- `ornith-1.0-35b-jang_4m`
- `qwen3.6-27b-mxfp4`

It also exposed newer OpenAI ChatGPT routes such as:

- `openai-chatgpt/gpt-5.6-sol-wm`
- `openai-chatgpt/gpt-5.6-terra-wm`
- `openai-chatgpt/gpt-5.6-luna-wm`

The older preferred names `openai-chatgpt/gpt-5.4-mini` and
`openai-chatgpt/gpt-5.5` were not present in the live model list.

## External Provider Boundary

The OpenAI-backed Osaurus route was not used for extraction. The approval
reviewer rejected that path because it would transmit the allowlisted corpus to
an external OpenAI-backed destination. This reinforced that the repository needs
a local or explicitly authorized extraction path for knowledge-graph refreshes.

## Local Provider Experiments

Several local Osaurus model attempts shaped the design:

- A sandboxed `graphify extract` failed to connect to the loopback endpoint with
  `[Errno 1] Operation not permitted`. Rerunning with explicit loopback
  escalation allowed Graphify to reach local Osaurus.
- `foundation` was reachable for simple chat but exceeded context limits on
  required files such as `AGENTS.md` and `AGENTS.local.md`.
- `qwen3.6-27b-mxfp4` was reachable but did not return the first Graphify chunk
  in a reasonable interactive window.
- `gemma-4-26b-a4b-it-jang_4m` was reachable and answered a tiny chat probe, but
  failed Graphify's extractor contract on real chunks.

The Gemma failure was especially informative. When Graphify sent
instruction-like files as corpus content, Gemma responded with acknowledgements
such as "I have read and understood..." instead of strict semantic extraction
JSON. Graphify then treated the responses as invalid or hollow and attempted
adaptive splitting, but single-file chunks still failed the schema contract.

## Subagent Extraction Discussion

The next option considered was using subagents to process files and feed their
results into Graphify.

The conclusion was yes, with an important boundary: subagents should not produce
loose summaries that are later fed to Graphify. That would weaken provenance and
make inferred edges harder to audit. Instead, subagents should produce
Graphify-compatible semantic extraction JSON directly:

- `nodes`
- `edges`
- `hyperedges`
- source provenance
- confidence and relation metadata
- evidence handles where available

The parent should validate each chunk before merge and preserve deterministic
ordering regardless of worker completion order.

## Additional Codex CLI Copies Discussion

The idea of spinning out additional Codex CLI copies to multiply the subagent
limit to "10 at a time" was rejected as the wrong first design.

The likely failure modes were:

- multiple processes writing to the same staging files;
- duplicated or missed chunks without a single authoritative manifest;
- fragmented provenance across transcripts;
- harder cleanup and retry accounting;
- higher risk of mutating accepted graph state before validation.

The safer design is a bounded worker pool with per-worker output roots,
manifests, locks where needed, and a single parent merge step. That design may
still achieve ten-at-a-time execution, but through a package-owned workflow
rather than ad hoc nested Codex sessions.

## DAR LLM Interface Tool Discussion

The design then shifted to using DAR's own LLM interface to build a
task-specific tool. This fits the package better because DAR already owns:

- model adapter selection;
- registry-mediated tool exposure;
- iterative model-tool loop behavior;
- subagent/workflow-as-tool patterns;
- approval, tracing, guardrails, and result shaping;
- fake-testable collaborators.

The proposed feature is therefore not "Graphify calls a model." It is "Graphify
detects the corpus, DAR extracts semantic graph facts in a controlled parallel
workflow, and Graphify consumes the staged artifacts."

## Stock Graphify Workflow vs OpenAI-Compatible Endpoint

Two integration options were compared.

### Stock-compatible artifact producer

The artifact producer emits the semantic JSON Graphify expects internally and
then lets Graphify run its normal graph construction, clustering, reporting,
curation, diagnostics, query, and promotion behavior.

Benefits:

- keeps Graphify as graph engine;
- lets DAR own chunking and parallel worker control;
- allows strict schema validation before merge;
- makes prompt-injection isolation explicit;
- keeps provenance and audit under one parent run;
- avoids pretending that DAR is a model provider.

This is the recommended first release.

### OpenAI-compatible endpoint

A DAR-backed OpenAI-compatible endpoint would make Graphify believe DAR is a
chat-completions provider.

Benefits:

- minimal change to Graphify invocation;
- transparent to Graphify's existing `--backend openai` path.

Costs:

- hides extraction control behind a generic chat facade;
- recreates the Gemma failure mode unless the endpoint intercepts and rewrites
  prompts;
- makes chunk validation and retry behavior indirect;
- adds server lifecycle and provider-emulation complexity;
- is harder to test as a small package-owned tool.

Endpoint emulation remains a possible future adapter, but not the preferred
first release.

## Package Extra Discussion

The feature should live behind a `tools` extra rather than the base package
install. That keeps the base runtime small while allowing users who want
package-owned exemplar tools to install them explicitly.

The extra should not make the tool ambient. A caller must still opt into the
tool by registering it in the effective `ToolRegistry` for a workflow or node.

Whether `dynamic-agent-runner[tools]` should depend on Graphify remains an
implementation-planning question. The first release can likely treat Graphify as
an external executable and focus on producing compatible staged artifacts.

## Relationship to Existing Specs

This feature uses existing spec boundaries rather than creating a new runtime
architecture:

- `subagent-tool-pack` owns bounded delegation mechanics.
- `iterative-agent-loop-runtime` owns model-tool loop execution and future
  budget accounting.
- `llm-step-interpreter-middleware` remains a separate optional code-execution
  surface; this feature does not require an interpreter.
- `approval-interruption-resume` and `live-guardrail-execution` own approval and
  guardrail behavior.
- `hash-chained-governance-audit` is a future audit stream that could later
  record extraction decisions, but is not required for the first release.
- `rag-orchestration-contract` remains caller-owned retrieval orchestration; this
  feature produces graph-building artifacts, not a RAG runtime.

## Recommended First Slice

The first slice should be deliberately small:

1. add the `tools` extra surface;
2. add the package-owned Graphify semantic extractor helper;
3. accept a manifest and write to a candidate output root;
4. use fake workers in tests;
5. validate strict JSON and source provenance;
6. merge deterministic staged semantic artifacts;
7. document the Graphify handoff.

Parallelism greater than the current in-process limit and any OpenAI-compatible
endpoint should wait until the artifact path is proven.
