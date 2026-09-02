---
name: agent-environment-health
description: Use for read-only health audits of coding-agent operating environments: instructions, runtime config, hooks, MCP/tool exposure, skills/plugins, memory routing, verifier entrypoints, generated mirrors, and stale guidance; not for agent design, codebase architecture health, runtime repair, external skill adoption, or AGENTS.local edits.
---

# agent environment health

Use this skill for report-only audits of the environment a coding agent runs
inside: instructions, runtime configuration, hooks, MCP or tool exposure,
skills, plugins, memory routing, verifier entrypoints, generated mirrors, and
stale durable guidance.

This is a specialized standalone skill. It finds evidence-backed health issues
and routes follow-up work to the owner. It does not edit files, run installers,
repair runtimes, execute project test suites, publish, install, refresh
generated mirrors, or mutate external systems unless the user separately asks
for that follow-up action.

## Relationship to adjacent skills

- Use `architecture-health-scan` for codebase design health: shallow modules,
  scattered behavior, dependency leaks, duplicated state transitions, and
  fragile tests.
- Use `agent-development` for designing agents, agent architectures, tool
  contracts as part of an agent design, memory envelopes, and evaluation plans.
- Use `agents-local-guidance` for marker-managed `AGENTS.local.md` edits.
- Use `skill-adoption-gate` for external skill or plugin-source adoption
  reviews.
- Use `plugin-runtime-lifecycle` for durable plugin runtime verify, install,
  update, repair, or rollback work.
- Use `memory-bank-maintenance` or `obsidian-memory` for memory content,
  contradiction, promotion, consolidation, or write-back work.
- Use `ci-cd-and-automation` for pipeline, hook, or quality-gate design.
- Use `security-and-hardening` for concrete trust-boundary, credential, secret,
  dependency, or LLM/tool-abuse hardening.

## When to use

Use this skill when the user asks to:

- audit why an agent setup is rotting, inconsistent, or hard to trust;
- check coding-agent instruction drift across repository and local guidance;
- inspect hooks, MCP servers, tool permissions, or runtime config for surprising
  exposure;
- review whether installed or repo-local skills, plugins, memory, generated
  mirrors, and verifier commands still line up;
- produce a read-only health report before deciding what repair work to split
  out.

Do not use it for ordinary code review, app debugging, codebase architecture
cleanup, adopting an external skill, designing a new agent, editing local
instructions, repairing a plugin runtime, or refreshing memory content.

## Workflow

### 1. Declare scope and authority

Name the exact repository, home/config area, plugin root, skill set, memory
surface, or verifier surface being audited. State whether the pass is shallow
or deep, and keep it read-only.

If the requested scope includes secrets, credentials, private traces,
production resources, or mutation, stop and ask for a narrower or separately
authorized operation.

### 2. Inventory only relevant surfaces

Inspect the smallest set that can answer the request:

- repository and local agent instructions;
- runtime config, hooks, MCP/tool permissions, and approval policy;
- repo-local and installed skills or plugins, including source pins and
  generated mirrors when visible;
- memory routing surfaces such as repo-local memory, Obsidian memory, imported
  memory, and state-export artifacts;
- documented verifier entrypoints, wrapper scripts, CI jobs, and recent
  captured output when provided.

Do not run installers, project test suites, generators, mirror refreshers, or
candidate scripts just to complete the audit. If execution is necessary,
report the missing evidence and route the follow-up separately.

### 3. Check health signals

Prioritize evidence for:

- conflicting or duplicated instructions across repository, local, installed,
  and generated surfaces;
- broad auto-trust, permission, hook, MCP, or tool exposure that exceeds the
  stated workflow;
- unpinned or unreviewed skill, plugin, script, package, or memory supply-chain
  inputs;
- stale generated mirrors, published copies, installed copies, or projection
  outputs that no longer match source;
- hollow verifier wrappers that print success without exercising the real path;
- stale captured output, temporary paths, or async completion claims presented
  as current validation;
- broken local Markdown references, missing support files, or renamed
  capabilities still referenced by routing text;
- repeated fix chains only when evidence shows the same invariant or failure
  layer recurring.

Do not report file counts, TODO counts, directory size, or unusual layout as a
finding unless it is tied to a concrete trust, routing, verification, or
maintenance failure.

### 4. Classify findings

Use three severities:

- `critical` — current agent execution can violate scope, expose secrets,
  mutate unexpectedly, or rely on a false green signal.
- `structural` — routing, source-of-truth, generated state, or verifier
  evidence is inconsistent enough to mislead future agents.
- `incremental` — cleanup would reduce confusion, but current behavior remains
  understandable and bounded.

Every finding needs a path, setting, command, or observed artifact as evidence.
If the evidence is missing, list it as an unavailable check rather than a
finding.

### 5. Route repairs outward

For each finding, name the follow-up owner:

- instruction edits -> `agents-local-guidance`;
- external skill review -> `skill-adoption-gate`;
- installed plugin repair -> `plugin-runtime-lifecycle`;
- agent design change -> `agent-development`;
- pipeline or hook redesign -> `ci-cd-and-automation`;
- security hardening -> `security-and-hardening`;
- memory correction -> `memory-bank-maintenance` or `obsidian-memory`;
- codebase design issue -> `architecture-health-scan` or `codebase-design`.

## Output shape

```text
Scope:
Mode: shallow | deep
Surfaces inspected:
Unavailable checks:
Findings:
- Severity: critical | structural | incremental
  Evidence: <path, setting, command, or artifact>
  Impact: <why this can mislead or break agent work>
  Owner: <follow-up skill or workflow>
  Next check: <smallest safe proof or repair step>
No-finding notes: <important inspected surfaces that were clean>
```

The audit is complete when scope, inspected surfaces, unavailable checks, and
evidence-backed findings are explicit, and every repair is routed without
turning the audit into an implicit mutation.
