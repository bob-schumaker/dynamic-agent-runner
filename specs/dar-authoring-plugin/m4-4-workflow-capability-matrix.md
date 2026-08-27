# M4.4 Workflow Capability Matrix

This reference defines the workflow features the clean-Codex author-then-run
harness may request, the minimum shape of authoring input for each, and the
expected wrapper outcome. It distinguishes a package declaration from
host-owned provisioning: a skill may generate a requirement, but it cannot
select a local path, create a profile, start a server, discover an MCP surface,
provide a credential, or change approval policy.

## Common Authoring Input

Every positive authoring case supplies a bounded task purpose, expected output
schema, one human-configured local-model profile requirement, finite limits, and
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
  profile_requirement: <human-configured local profile capability>
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

| Capability | Additional authoring input | Expected status / host prerequisite |
| --- | --- | --- |
| Basic reasoning or document summary | Task instructions, examples, declared document artifact role, output shape | Positive with a compatible local model profile; no tools required. |
| No-tool multi-step graph | Named `llm_step` and `decision_step` behavior; routes, intermediate outputs, finite step bound | Package graph validation and compatible model profile. |
| Tool-using graph | A declared tool-use node plus its bounded routes and output rules | The tool's corresponding host binding and gate, in addition to graph validation. |
| Structured terminal output | JSON schema or representative result | Output contract must match `task_invocation` terminal schema. |
| Package-local skill | Skill purpose, instructions, distributable supporting files, nodes using its `skill_refs` | Bundle only under `skill-bundle/`; no external skill path. |
| Read-only MCP tool | Stable connection requirement, reviewed semantic tool identifier, input/output schemas, call cap, result-use rules | G2 human-configured/authenticated connection and reviewed surface snapshot. |
| MCP mutation | Read-only inputs plus side-effect class, approval requirement, timeout/failure policy, idempotency expectation, and per-argument provenance sources | G2 plus G5. `workflow_auto`, `--dry-run`, and `--ask` are wrapper modes, not package-provisioned choices. |
| File-backed task | Named artifact roles, accepted media types, encoding and size requirements, allowed tool argument uses | G4 trusted ingress from a configured caller input root. |
| Hybrid input | Structured field schema/mappings, original-prompt precedence, bounded `additional_context` | Wrapper seals all invocation input. `additional_context` cannot supply destination, authorization, capability, or external-identity values. |
| Tool argument provenance | For each argument: sealed field, original-prompt span, artifact role, package constant, or permitted content transform | G5 verifies `ArgumentProvenanceEnvelope`; raw or unverifiable values fail before dispatch. |
| ReAct/tool loop | Declared tools, stopping condition, bounded total calls, final-output rule | Every tool must be declared, host-bound, and within the task call limit. |
| OAuth-backed MCP connection | OAuth requirement and least scope by stable connection requirement | Human-only control-plane setup and G2. For OAuth-advertising servers, standards discovery and dynamic registration require `mcp-oauth-discovery-registration`. The authoring request contains no endpoint, redirect listener, code, token, client ID, or secret. |
| Package portability | Package name, export request, and explicitly distributable material | M4 records pre-publication unavailability. M8 proves recipient-host manifest verification and any required publisher-signature check; ZIP is delivery data, not an executable bundle. |
| Evaluation | Acceptance cases, deterministic assertions, rubric, judge or human-review policy, regression threshold | Evaluation runs through tests/external harness, not DAR execution. |
| Guardrails | Guardrail identifier, phase, tripwire behavior, failure message | Unsupported guardrail phases are capability-unavailable; broader profiles are deferred. |
| Context pruning/pipeline | Context sources, ordering, byte/token budget, pruning policy | Conceptually package metadata; broader wrapper context profiles are deferred. |
| Scratch workspace | Needed read/write/delete operations and output-artifact contract | Deferred: current v1 descriptor accepts `scratch_access: none` only. |
| Durable session or continuation | Session identity, retained state schema, turn/reset/retention policy | Deferred: wrapper does not claim durable sessions or graph-preserving interruption continuation. |
| Collaboration, subagents, or agent-as-tool | Roles, handoffs, budgets, aggregation schema | Deferred: return capability-unavailable rather than claim a multi-agent council or `ask_llm` behavior. |
| Retrieval, embedding, or RAG | Embedding-profile requirement, document roles, index/retrieval contract, result schema | Deferred until a host embedding/vector adapter exists; never invent a Hugging Face invocation. |
| Computer use, coding, shell, web, or other custom host tools | Task-specific schema, allowed operation set, side-effect/provenance/limit policies | Requires a separately implemented and reviewed host binding; no generic tool console. |
| Native approval interruption/resume | Requested pause point, approval payload, resume semantics | Wrapper currently supports only handler-bound `--ask`; it does not expose DAR continuation/replay. |

## Harness Interpretation

M4.4 in [`plan.md`](plan.md) is the sole contract for scenario manifests,
fixture isolation, status classification, evidence, review, and fake-provider
policy. This matrix defines only feature inputs and gates.
