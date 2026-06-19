# Web Tool Pack Specification

## Metadata

- Feature slug: `web-tool-pack`
- Mode: `light`
- Artifact type: implemented feature specification
- Status: implemented v1 baseline
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related artifacts:
  - `specs/capability-status-report/spec.md`
  - `specs/live-guardrail-execution/spec.md`
  - `specs/mcp-runtime-integration/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/rag-orchestration-contract/spec.md`
  - `src/dynamic_agent_runner/models.py`
  - `src/dynamic_agent_runner/registry.py`
  - `src/dynamic_agent_runner/executor.py`

## Objective

Define an explicit, opt-in built-in web tool pack so workflows can use standard
web search and web read/fetch capabilities through the existing
`ToolRegistry` boundary without treating network access as an ambient runtime
permission.

The feature fills the current gap between portable `tool_type` metadata such as
`web_search` and `web_fetch` and actual callable tools available to workflows.

## Implementation Status

The v1 baseline is implemented by `create_web_registry(...)`,
`WebToolPolicy`, and related registry helpers in
`src/dynamic_agent_runner/registry.py`, with exports from
`dynamic_agent_runner`.

Completed:

- opt-in `web_search` and `web_fetch` registry pack
- required injected search and fetch clients
- bounded normalized search and fetch result mappings
- URL scheme and exact-domain policy checks
- fake-client tests and import coverage

Deferred:

- redirects, timeout enforcement, local/private network rejection, response
  byte limits, robots/terms posture, and provider adapters
- trace redaction beyond ordinary registry/tool behavior
- capability/status states for disabled, missing-client, live, and
  policy-rejected web pack configurations
- optional `web_extract`/readability behavior

## Problem Statement

The runtime already supports:

- portable tool categories including `web_search` and `web_fetch`
- caller-registered tools through `ToolRegistry`
- explicit built-in registry packs, currently represented by read-only
  `local_workspace`
- approval, guardrail, trace, and capability-status surfaces

What is missing is a package-owned standard web pack analogous to
`local_workspace`. Without one, every caller must invent its own search/fetch
tool names, schemas, result shape, redaction posture, citation metadata, and
network policy. That weakens workflow portability and makes capability reporting
less useful.

## Scope

This feature covers:

1. opt-in built-in web registry pack enablement
2. standard tool ids, names, schemas, and portable `tool_type` assignment
3. injected provider/client interfaces for search and fetch/read behavior
4. result normalization for model-facing summaries, raw payload references,
   source URLs, titles, snippets, status codes, content type, and truncation
   metadata
5. network policy for allowed schemes, domain restrictions, redirects, timeouts,
   content-size limits, and robots/terms-of-use posture
6. approval and guardrail integration for risky or externally mutating network
   behavior
7. trace redaction and capability/status reporting
8. fake-client unit tests only

## Non-Goals

This feature must not introduce:

- ambient web/network access for all workflows
- live web calls in unit tests
- browser automation, login/session handling, screenshots, JavaScript execution,
  or interactive browsing
- write-capable network actions such as form submission, posting, uploading,
  purchasing, or API mutation
- scraping policy that bypasses caller/deployment restrictions
- provider-owned search ranking guarantees
- built-in RAG indexing, embeddings, crawling, or persistent web caches
- MCP transport or remote-server lifecycle management

Browser automation remains out of scope. MCP-provided web tools remain governed
by `mcp-runtime-integration`; this pack owns only package-provided local
registry entries backed by caller-injected web clients.

## Proposed Tool Pack Shape

The first built-in pack should be named `web` and remain disabled by default.

Suggested v1 tool ids:

- `web_search` — search the web and return bounded result metadata.
- `web_fetch` — fetch a single URL and return bounded normalized content or
  metadata.
- `web_extract` — optional follow-up tool for content extraction/readability
  when raw fetch and text extraction should be separated.

The v1 implementation may start with only `web_search` and `web_fetch` if that
keeps the first slice smaller.

Conceptual API shape:

```python
from dynamic_agent_runner import create_web_registry

registry = create_web_registry(
    search_client=my_search_client,
    fetch_client=my_fetch_client,
    policy=WebToolPolicy(
        allowed_schemes=("https",),
        max_fetch_bytes=1_000_000,
        timeout_seconds=10,
        allowed_domains=("docs.python.org", "platform.openai.com"),
    ),
)
```

Names are draft. Implementation planning should keep provider/client interfaces
small and avoid adding live search provider dependencies to the core package.

## Functional Requirements

### FR-1: Keep Web Tools Explicitly Opt-In

Given no web pack is enabled and no caller registered equivalent tools, when a
workflow references `web_search` or `web_fetch`, then execution must fail through
the existing unavailable-tool path.

Given the caller enables the web pack, when registry preparation runs, then web
tools are registered only in the effective registry and are still exposed only
to nodes that reference them.

### FR-2: Require Injected Web Clients

Given the web pack is enabled, when executable web search or fetch behavior is
needed, then the caller must supply explicit client/collaborator objects or
approved provider configuration.

The core package must not hard-code a search provider, fetch library with hidden
network defaults, API key lookup, or live browser backend in v1.

### FR-3: Normalize Search Results

Given `web_search` returns results, when those results are passed to workflow
state or the model, then each result must use a bounded package-owned shape that
can include title, URL, snippet, rank, source/provider id, retrieved timestamp,
and optional freshness or confidence metadata.

Raw provider payloads must not be model-visible by default.

### FR-4: Normalize Fetched Content

Given `web_fetch` retrieves a URL, when content is returned, then the result must
include normalized URL, status, content type, title when available, text or
summary preview within configured limits, truncation metadata, and redacted
diagnostics.

Binary content, oversized responses, unsupported content types, and decode
failures must fail clearly or return metadata-only results according to policy.

### FR-5: Enforce Network Policy

Given web tools are enabled, when a request is made, then policy must validate at
least URL scheme, hostname/domain restrictions, redirects, timeout, response
size, and maximum result count before model-visible output is produced.

Disallowed targets must fail closed with package-owned errors or `ToolResult`
failures that do not leak secrets.

### FR-6: Preserve Approval, Guardrail, and Sandbox Boundaries

Given network access may leak private information or trigger external effects,
when web tools are used, then they must carry explicit policy metadata for side
effect, approval, sandbox/network, timeout, retry, and failure behavior.

Search and read-only fetch may default to no approval only when deployment policy
marks them trusted. Redirects to unapproved hosts, authenticated URLs, local
network targets, and non-HTTPS schemes should be approval-required or rejected by
default.

### FR-7: Report Capability Status

Given a workflow references web tools, when capability status is generated, then
the report must distinguish disabled web pack, enabled pack with missing
clients, enabled live clients, policy-rejected configuration, and metadata-only
web tool declarations.

### FR-8: Keep Traces Bounded and Redacted

Given web tools run, when trace events are emitted, then traces must include
tool id, normalized URL or query preview, provider id, status, byte counts,
duration, truncation, and error category without dumping full page content, raw
provider payloads, credentials, cookies, authorization headers, or query secrets.

## Acceptance Criteria

- `web` built-in pack is disabled unless explicitly enabled.
- `web_search` and `web_fetch` resolve through `ToolRegistry` only.
- Missing injected clients fail clearly before pretending web tools are live.
- Search results use a bounded package-owned result shape.
- Fetch results include source, content metadata, limits, and truncation facts.
- URL/network policy rejects disallowed schemes, hosts, redirects, and oversized
  responses.
- Capability/status distinguishes disabled, missing-client, live, and
  policy-rejected web pack states.
- Traces and model-facing outputs redact secrets and avoid raw full-page dumps.
- Unit tests use fake search/fetch clients and perform no live network calls.

## Implementation Planning Notes

- Start with RED tests in `tests/test_registry.py` for pack registration,
  disabled-by-default behavior, missing clients, and policy rejection.
- Add capability/status tests in `tests/test_capabilities.py` before reporting
  the pack as live.
- Keep implementation near existing built-in pack mechanics in
  `src/dynamic_agent_runner/registry.py` unless size justifies a dedicated
  module such as `web_tools.py`.
- Reuse `ToolType.WEB_SEARCH` and `ToolType.WEB_FETCH`; do not add new portable
  tool types unless a concrete result shape requires it.
- Treat web extraction/readability as a follow-up unless needed for a minimal
  useful `web_fetch`.
- Coordinate future RAG work through `rag-orchestration-contract`: web tools may
  supply retrieval evidence, but they must not become runner-owned indexing or
  embedding infrastructure.

## Validation Checklist

Implemented v1 validation includes:

- tests for enabled pack with fake clients
- tests for missing client failures
- tests for search result normalization and maximum-result limits
- tests for fetch content normalization and truncation
- tests for scheme and exact-domain policy

Deferred validation should include:

- tests for scheme, domain, redirect, local-network, timeout, and size policy
- tests for trace redaction
- tests for capability/status web pack states

Relevant commands:

```bash
poetry run pytest tests/test_registry.py tests/test_import.py -q
poetry run ruff check src tests
```

## Open Questions

- Should v1 include both `web_search` and `web_fetch`, or start with `web_fetch`
  only and leave search provider integration to callers?
- Should the built-in pack include an optional `web_extract` tool, or should text
  extraction be part of `web_fetch` policy?
- What default domain policy should the CLI expose, if any?
- Should local/private network targets be rejected unconditionally by default?
- Should provider-specific search adapters live in optional extras or remain
  caller-owned indefinitely?
