# M4.4 Workflow Capability Matrix

This reference defines the workflow features the clean-Codex author-then-run
harness may request, the minimum shape of authoring input for each, and the
expected wrapper outcome. It distinguishes a package declaration from
host-owned provisioning: a skill may generate a requirement, but it cannot
select a local path, create a profile, start a server, discover an MCP surface,
provide a credential, or change approval policy.

## Common Authoring Input

Every positive authoring case supplies a bounded task purpose, expected output
schema, one human-configured execution-profile requirement, finite limits, and
either inline examples or a selected `AuthoringMaterialSet`. It may additionally
declare a hybrid invocation contract:

```yaml
invocation:
  prompt: <runtime user request>
  structured_fields: <optional JSON schema and field mappings>
  workspace_artifacts: <optional named roles and media types>
  additional_context: <optional bounded plain text>
output:
  schema: <terminal output schema>
model:
  profile_requirement: <human-configured execution-profile capability>
limits:
  max_steps: <finite positive integer>
```

The generated package contains `agent-design.md`, `agent-runtime.yaml`,
`agent-graph.mmd`, `WorkflowDescriptor`, and, where applicable, package-local
skills, a tool index, evaluation artifacts, and a content manifest. The
skill-invoked CLI remains deliberately narrow: a selected saved package name,
prompt, and declared inputs only. DAR internally binds opaque artifacts and
bounded `additional_context` after trusted preparation. The command cannot
replace the package's model, tool, skill, or connection requirements.

## Capability Matrix

`support_status` determines successor acceptance: `supported` requires a
positive end-to-end scenario; `conditional` requires a positive scenario with
the listed host fixture and an unavailable result without it; `deferred`
requires only its declared unavailable or refusal scenario. A scenario may
cover one or more capability IDs.

| ID | Capability | Support status | Additional authoring input | Expected status / host prerequisite |
| --- | --- | --- | --- | --- |
| `basic-reasoning` | Basic reasoning or document summary | supported | Task instructions, examples, declared document artifact role, output shape | Positive with a compatible host execution profile; no tools required. |
| `no-tool-multi-step` | No-tool multi-step graph | supported | Named `llm_step` and `decision_step` behavior; routes, intermediate outputs, finite step bound | Package graph validation and compatible model profile. |
| `tool-using-graph` | Tool-using graph | conditional | A declared tool-use node plus its bounded routes and output rules | Corresponding host binding and gate, in addition to graph validation. |
| `structured-terminal-output` | Structured terminal output | supported | JSON schema or representative result | Output contract must match `task_invocation` terminal schema. |
| `package-local-skill` | Package-local skill | supported | Skill purpose, instructions, distributable supporting files, nodes using its `skill_refs` | Bundle only under `skill-bundle/`; no external skill path. |
| `read-only-mcp-tool` | Read-only MCP tool | conditional | Stable connection requirement, reviewed semantic tool identifier, input/output schemas, call cap, result-use rules | G2 human-configured/authenticated connection and reviewed surface snapshot. |
| `mcp-mutation` | MCP mutation | conditional | Read-only inputs plus side-effect class, per-invocation approval policy, timeout/failure policy, idempotency expectation, and per-argument provenance sources | G2 plus G5; `workflow_auto`, `--dry-run`, and `--ask` enforce package policy. |
| `file-backed-task` | File-backed task | conditional | Named artifact roles, accepted media types, encoding and size requirements, allowed tool argument uses | G4 trusted ingress from a configured caller input root. |
| `hybrid-input` | Hybrid input | supported | Structured field schema/mappings, original-prompt precedence, bounded `additional_context` | Wrapper seals all invocation input. |
| `tool-argument-provenance` | Tool argument provenance | conditional | For each argument: sealed field, original-prompt span, artifact role, package constant, or permitted content transform | G5 verifies `ArgumentProvenanceEnvelope`; raw or unverifiable values fail before dispatch. |
| `react-tool-loop` | ReAct/tool loop | conditional | Declared tools, stopping condition, bounded total calls, final-output rule | Every tool must be declared, host-bound, and within the task call limit. |
| `oauth-mcp-connection` | OAuth-backed MCP connection | conditional | OAuth requirement and least scope by stable connection requirement | Human-only control-plane setup and G2; authoring input has no endpoint, redirect listener, code, token, client ID, or secret. |
| `package-portability` | Package portability | deferred | Package name, export request, and explicitly distributable material | No successor portability/publication claim: the former M8 publication path is retired. ZIP remains delivery data, not an executable bundle. |
| `evaluation` | Evaluation | supported | Acceptance cases, deterministic assertions, rubric, judge or human-review policy, regression threshold | The package contains checked-in evaluation fixtures; after invocation the harness runs their deterministic assertions and records the result. No judge-model call is required or implied. |
| `guardrails` | Guardrails | conditional | Guardrail identifier, phase, tripwire behavior, failure message | Supported phases are exactly caller-registered `input` and validated `tool_input`; each requires its corresponding registry fixture and abort trace. Any other phase is capability-unavailable. |
| `context-pruning-pipeline` | Context pruning/pipeline | deferred | Context sources, ordering, byte/token budget, pruning policy | Broader wrapper context profiles are deferred. |
| `scratch-workspace` | Scratch workspace | deferred | Needed read/write/delete operations and output-artifact contract | Current v1 descriptor accepts `scratch_access: none` only. |
| `durable-session-continuation` | Durable session or continuation | deferred | Session identity, retained state schema, turn/reset/retention policy | No durable sessions or graph-preserving interruption continuation. |
| `collaboration-subagents` | Collaboration, subagents, or agent-as-tool | deferred | Roles, handoffs, budgets, aggregation schema | Capability-unavailable; do not claim a multi-agent council or `ask_llm` behavior. |
| `retrieval-embedding-rag` | Retrieval, embedding, or RAG | deferred | Embedding-profile requirement, document roles, index/retrieval contract, result schema | No host embedding/vector adapter; never invent a Hugging Face invocation. |
| `custom-host-tools` | Computer use, coding, shell, web, or other custom host tools | deferred | Task-specific schema, allowed operation set, side-effect/provenance/limit policies | No generic tool console or separately reviewed binding in this scope. |
| `native-approval-resume` | Native approval interruption/resume | deferred | Requested pause point, approval payload, resume semantics | Only handler-bound `--ask` is available; no continuation/replay API. |

## Harness Interpretation

M4.4 in [`plan.md`](plan.md) records the retired plugin's historical scenario
and evidence contract. The successor-only acceptance contract, task list, and
full-matrix coverage requirement are owned by
[`agent-engineering-plugin-migration`](../agent-engineering-plugin-migration/spec.md).
This matrix defines feature inputs, gates, IDs, and support statuses for both
records.
