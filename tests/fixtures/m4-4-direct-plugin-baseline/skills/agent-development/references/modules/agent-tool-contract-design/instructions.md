---
name: agent-tool-contract-design
description: Use to design agent tools, MCP contracts, and CLIs for safe selection, calls, parsing, recovery, and composition.
---

# agent tool contract design skill

Use this skill when the main task is to design or review a tool contract for an
AI agent, including MCP tools, function-calling tools, command-line tools, or
other deterministic capabilities exposed to model-driven workflows.

This is a specialized standalone skill. It owns model-facing tool contract
mechanics, not implementation of the tool internals or live source-system
operations.

## Relationship to adjacent skills

- Use `corpus/capabilities/agent-development/SKILL.md` when tool design is part
  of a broader agent architecture, runtime, memory, safety, or evaluation
  design.
- Use this skill when the tool contract itself is the main design problem:
  naming, trigger boundaries, inputs, outputs, errors, safety, and agent
  selection behavior.
- Use `corpus/capabilities/mcp-server-wrapper/SKILL.md` only for wrapper
  diagnostics or low-level stdio MCP invocation mechanics.
- Use `corpus/capabilities/source-driven-development/SKILL.md` when the tool
  contract depends on current official framework, API, SDK, or standard
  behavior.
- Use `corpus/capabilities/security-and-hardening/SKILL.md` when a proposed
  tool exposes sensitive data, auth, external mutation, uploads, shell access,
  destructive operations, or other security-critical behavior.

## References

- `references/agent-friendly-cli.md` - load when the tool is a command-line
  interface or when CLI output, exit codes, flags, non-interactive behavior, or
  shell-safety conventions are in scope.

## When to use

Use this skill when the user asks to:

- design a tool API that an agent will call
- improve or audit a tool description, schema, output, or error contract
- decide whether to split, merge, namespace, or hide tools from an agent
- design an MCP tool contract before implementation
- make a local CLI reliable for agent invocation
- diagnose repeated agent misuse of a tool when the issue is contract design

Do not use this skill for ordinary library API design with no agent caller, live
MCP source-system operations, broad agent architecture, security review of a
dangerous tool, or implementation debugging where the contract is already clear.

## Workflow

### 1. Define the agent job

State the concrete job the agent must accomplish:

- user request shapes that should trigger the tool
- tasks that should not trigger it
- expected success result
- required evidence, side effects, and mutation authority
- runtime owner for permissions, retries, timeouts, and audit logs

If the intended workflow is unclear, resolve that before designing parameters.

### 2. Choose the exposure shape

Pick the smallest unambiguous exposure:

- one workflow-level tool when the agent should not choose among substeps
- separate tools when the actions have distinct triggers, permissions, or
  failure modes
- a namespace when related tools must coexist with other domains
- a hidden runtime-only helper when the model should not call it directly
- a CLI wrapper only when process boundaries or human reuse justify it

Avoid overlapping tools whose selection boundary would be unclear to a human
reviewer. If the distinction cannot be explained in one sentence, redesign the
set before adding descriptions.

### 3. Write the model-facing contract

For each exposed tool, define:

- stable name and namespace
- one-sentence purpose
- explicit "use when" and "do not use when" boundaries
- input schema with required fields, constraints, defaults, and examples
- output schema with success shape, empty result behavior, and provenance
- response-size controls such as `summary`, `detailed`, or field selection
- side effects, permissions, cost, latency, and approval requirements
- terminal behavior: whether the tool can complete the overall task

Descriptions should tell the agent what the tool does, when to use it, what to
provide, and what it will receive. Avoid vague verbs such as "manage",
"process", or "handle" unless the rest of the contract makes the behavior
specific.

### 4. Design recovery behavior

Make failures actionable:

- machine-readable error codes
- human-readable message
- correction or retry suggestion
- retryability and idempotency signal
- missing permission or precondition details
- partial-success and rollback or cleanup behavior

Do not return a generic failure that forces the agent to guess the next call.

### 4a. Bound federated read contracts

For a discovery or aggregation tool that consults configured upstream tools or
MCP servers, define the smallest explicit federation contract before extending
the tool set:

- versioned request and response shapes, stable namespaced record identity, and
  deduplication or coexistence rules
- typed records that distinguish declarative metadata from executable actions;
  never embed credentials or authority-bearing instructions in a handoff field
- ordered provenance plus per-source attempt and outcome fields; define empty,
  malformed, timeout, partial, and unavailable behavior separately
- deterministic aggregate-result semantics and visible routing rationale so the
  agent does not mistake an incomplete result for exhaustive coverage
- configured/allowlisted upstreams, bounded traversal depth, cancellation or
  timeout behavior, and deterministic cycle handling
- the permission enforcement point, request-data sharing limits, and the rule
  that upstream credentials remain server-scoped rather than forwarded

Keep product judgments such as relevance or "sufficient coverage" observable
and narrow in an initial spike. Prefer a fixed routing predicate that the
response exposes over an unexplained confidence score. Record source attempt,
outcome category, elapsed time, candidate count, and routing decision without
retaining sensitive request payloads or credentials by default.

### 5. Place safety at the risky boundary

For each operation, define:

- read-only, write, destructive, privileged, or external side-effect level
- approval requirements and `dry-run` or preview behavior
- secret, credential, sensitive-path, prompt-injection, and data-leakage
  controls
- path traversal, shell metacharacter, oversized input, and batch-limit handling
- audit fields that let a reviewer reconstruct changed state

Keep high-risk action confirmation in deterministic code, not only in the model
prompt.

### 6. Test the contract with representative prompts

Before treating the design as ready, run a small behavior review:

- trigger prompts that should select the tool
- negative prompts that should avoid it
- ambiguous prompts that should ask for clarification
- invalid input examples and expected errors
- empty result and partial-failure cases
- federated read cases: no match, local success with remote timeout, malformed
  upstream response, and exhausted traversal budget
- high-risk mutation cases and approval gates

Revise names, descriptions, schemas, or tool grouping when failures indicate
selection ambiguity rather than implementation bugs.

## Output expectations

Return:

```text
Agent job:
Tool exposure shape:
Tool contracts:
Inputs and outputs:
Errors and recovery:
Safety and permissions:
Validation prompts:
Implementation handoff:
```

## Completion standard

This skill is complete when the tool set has clear trigger boundaries, every
exposed tool has a model-facing contract, output and error shapes are parseable,
recovery behavior is actionable, safety is enforced at deterministic
boundaries, and representative prompts show the agent can select or avoid the
tool correctly.
