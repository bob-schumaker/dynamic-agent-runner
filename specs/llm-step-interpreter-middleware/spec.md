# LLM Step Interpreter Middleware Future Feature Specification

## Metadata

- Feature slug: `llm-step-interpreter-middleware`
- Mode: `light`
- Artifact type: future feature specification / implementation-detail evaluation
- Status: proposed for future investigation; no interpreter selected
- Source context:
  - `specs/llm-step-interpreter-middleware/references/give-your-agents-an-interpreter.md`
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/plan.md`
  - `specs/dynamic-agent-runner/tasks.md`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/models.py`
  - `src/dynamic_agent_runner/registry.py`
  - `src/dynamic_agent_runner/openai_client.py`
  - `pyproject.toml`
  - local supporting checkout: `/Users/roschuma/Repos/github/deepagents/`
  - upstream repository: `https://github.com/langchain-ai/deepagents.git`

## References

- `specs/llm-step-interpreter-middleware/references/give-your-agents-an-interpreter.md`
  — supporting; use as the packaged source note that motivated this future
  feature evaluation
- `https://github.com/langchain-ai/deepagents.git` — supporting provenance;
  use as upstream context for the local Deep Agents checkout observations

## Objective

Evaluate and later prototype an optional interpreter middleware capability
for `llm_step` nodes so dynamic-agent workflows can reduce model-mediated round
trips,
keep intermediate working state out of model prompt history, and compose
allowlisted tool calls programmatically without exposing a full host sandbox.

This specification records the future feature idea only. It does **not**
choose an interpreter implementation and does **not** authorize implementation
yet.

## Local Deep Agents Reference Observations

The referenced Deep Agents repository is available locally at
`/Users/roschuma/Repos/github/deepagents/`, with upstream repository provenance
at `https://github.com/langchain-ai/deepagents.git`. That checkout is useful
supporting provenance for future investigation, but this future feature spec
should not depend on that machine-specific path for implementation. Any details
adopted from it should be summarized or converted into repository-local
requirements before implementation.

Read-only inspection found these relevant implementation details:

- `libs/code/pyproject.toml` defines a `quickjs` optional extra as
  `langchain-quickjs>=0.1.2,<0.2.0`.
- The lockfiles show `langchain-quickjs` depending on `quickjs-rs>=0.1.2,<0.2.0`
  with wheels for Python 3.11, 3.12, and 3.13 across several platforms. This is
  supporting evidence that QuickJS is a viable candidate to investigate, not
  a selection decision.
- `libs/code/deepagents_code/config.py` defines an `interpreter_ptc="safe"`
  preset limited to read-only tools (`read_file`, `glob`, `grep`) and excludes
  network, subagent dispatch, shell execution, file writes, and MCP write tools
  because PTC bypasses per-tool HITL/interrupt gates.
- `libs/code/deepagents_code/agent.py` resolves PTC configuration as disabled,
  `safe`, `all`, or an explicit tool-name list. It requires explicit unsafe
  acknowledgement for `all` when host tools would otherwise be approval-gated.
- `libs/code/deepagents_code/agent.py` wires `CodeInterpreterMiddleware` only in
  local mode, rejects pairing it with a remote sandbox in that release, and passes
  `tool_name="js_eval"`, timeout, memory limit, max PTC calls, max result chars,
  and a resolved PTC allowlist.
- `libs/partners/quickjs/langchain_quickjs/middleware.py` describes a persistent
  JavaScript REPL per LangGraph thread, backed by QuickJS contexts, with defaults
  such as 64 MiB memory limit, 5 second timeout, 256 max PTC calls, 4000 max
  result characters, optional console capture, and snapshotting between turns.
- `libs/partners/quickjs/langchain_quickjs/_ptc.py` exposes allowlisted tools as
  `tools.<camelCaseName>(input)` async functions and explicitly excludes the
  interpreter's own eval tool to prevent recursive `tools.eval(...)` calls.

Implication for this repository: Deep Agents' implementation reinforces the
importance of explicit allowlists, safe read-only presets, unsafe acknowledgements
for broad exposure, result and call budgets, and careful tracing of PTC calls that
do not naturally traverse the normal tool-execution path.

## Problem Statement

The current runtime executes `llm_step` nodes by rendering messages, exposing
OpenAI-compatible tool schemas, calling the OpenAI adapter, validating output
contracts, recording token usage, and emitting trace events. This is appropriate
for straightforward LLM calls, but some workflows may require many small tool
calls, batch filtering, fan-out/fan-in, or large intermediate state. Handling
those steps through repeated model-mediated turns can increase latency, token
usage, context pressure, and prompt-history noise.

An embedded interpreter could provide a constrained execution surface between
serial tool calls and full sandbox execution. The model could write a small
program that uses only bridged, allowlisted capabilities, keeps intermediate
values in interpreter state, and returns a compact result or evidence bundle to
the model context.

## Current Architecture Fit

The interpreter idea fits the repository only if it preserves existing runtime
boundaries:

- `src/dynamic_agent_runner/executor.py` owns `llm_step` execution, token-budget
  checks, output-contract validation, retry recording, state updates, and trace
  emission.
- `src/dynamic_agent_runner/registry.py` owns callable tool registration, per-node
  tool exposure, OpenAI schema conversion, and registry-authoritative invocation.
- `src/dynamic_agent_runner/models.py` intentionally preserves a small primitive
  node taxonomy: `llm_step`, `tool_use_step`, and `decision_step`.
- `src/dynamic_agent_runner/openai_client.py` owns the default official OpenAI
  adapter boundary.
- `specs/dynamic-agent-runner/spec.md` favors package-owned interfaces,
  OpenAI-first model execution, explicit tool registries, fail-closed safety, and
  optional dependencies only behind scoped requirements.

The likely integration point is optional middleware/configuration for `llm_step`,
not a new primitive node kind in the first design.

## Proposed Capability Shape

A future manifest extension might attach an interpreter to a specific
`llm_step`
by referencing an interpreter id from a caller-provided interpreter
registry or a manifest-declared interpreter metadata section:

```yaml
interpreters:
  - id: quickjs_experimental
    label: QuickJS Experimental Interpreter
    language: javascript
    adapter: caller.quickjs
    default_limits:
      max_tool_calls: 20
      timeout_ms: 2000
      max_result_bytes: 20000
      max_state_bytes: 50000
      snapshot: serializable_state_only

nodes:
  - id: analyze_documents
    kind: llm_step
    interpreter:
      enabled: true
      interpreter_id: quickjs_experimental
      mode: eval_tool
      tool_allowlist:
        - search_files
        - read_file
      limits:
        max_tool_calls: 10
```

The manifest-level `interpreters` section is metadata and policy only. It does
not make an interpreter executable by itself. A caller-provided interpreter
registry, or another explicitly approved source, must provide the actual runtime
adapter for `interpreter_id`.

Expected executor-level flow:

1. `_execute_llm_step(...)` detects an interpreter policy on the node or effective
   node behavior.
2. The model receives an explicit interpreter/eval capability in its prompt or
   tool surface.
3. Interpreter code runs in a constrained embedded runtime.
4. The interpreter exposes only explicit bridged capabilities, such as
   `tools.<tool_id>(...)`, derived from node-level tool exposure and runtime
   registry overrides.
5. Bridged tools route through the existing `ToolRegistry.invoke_tool(...)` path
   or a compatible successor interface.
6. Results, retries, trace events, token accounting, and output-contract
   validation remain package-owned.
7. The final interpreter result is returned to the model context or treated as
   the node output according to the finalized execution semantics.

## Custom Interpreter Interface

The runner should support caller-specified custom interpreters through a
package-owned interface rather than hard-coding a single backend. This mirrors
the
existing model-client and tool-registry approach: generated artifacts may declare
intent and policy, while the caller supplies executable adapters at runtime.

Conceptual Python API shape:

```python
from dynamic_agent_runner import (
    InterpreterDefinition,
    InterpreterRegistry,
    RegisteredInterpreter,
    run_agent_workflow,
)

registry = InterpreterRegistry()
registry.register(
    RegisteredInterpreter(
        definition=InterpreterDefinition(
            id="quickjs_experimental",
            language="javascript",
            side_effect="none",
            supports_snapshots=True,
        ),
        adapter=my_quickjs_adapter,
    )
)

result = run_agent_workflow(
    runtime="agent-runtime.yaml",
    prompt="Analyze the workspace.",
    tool_registry=tool_registry,
    interpreter_registry=registry,
)
```

Conceptual protocol shape:

```python
class InterpreterAdapter(Protocol):
    def create_session(
        self,
        *,
        node_id: str,
        definition: InterpreterDefinition,
        limits: InterpreterLimits,
        tool_bridge: InterpreterToolBridge,
        snapshot: bytes | None = None,
    ) -> InterpreterSession: ...

class InterpreterSession(Protocol):
    def evaluate(self, request: InterpreterRequest) -> InterpreterResult: ...
    def snapshot(self) -> bytes | None: ...
    def close(self) -> None: ...
```

The exact type names are provisional, but the interface should preserve these
responsibilities:

- `InterpreterDefinition` records non-executable metadata: id, label, language,
  adapter name, default limits, safety classification, snapshot support, and raw
  manifest metadata.
- `RegisteredInterpreter` combines an `InterpreterDefinition` with an executable
  adapter supplied by the caller.
- `InterpreterRegistry` resolves `interpreter_id` for `llm_step` nodes, applies
  runtime interpreter overrides, and fails closed for missing or disabled
  interpreters.
- `InterpreterToolBridge` exposes only effective allowlisted registry tools to the
  interpreter session and routes every call through the package-owned tool
  registry.
- `InterpreterRequest` carries code or DSL content, selected execution mode, node
  id, effective prompt context, and any serializable prior state.
- `InterpreterResult` carries the final value, optional stdout/stderr, structured
  metadata, tool-call records, snapshot payload, timeout/error information, and
  result-size accounting.

Custom interpreters may be implemented by callers using QuickJS, restricted
Python, a DSL, WebAssembly, a subprocess harness, or another backend, but the
runner should interact with them only through this package-owned interface.

## Functional Requirements

### FR-1: Preserve explicit capability boundaries

The interpreter MUST NOT expose host filesystem, network, shell, environment,
package installation, import/module loading, wall-clock, process APIs, or other
ambient capabilities by default.

Acceptance criteria:

- Given interpreter middleware is enabled with no allowlisted tools, when code
  runs, then it can only use language/runtime primitives.
- Given a node exposes tools through `available_tools` and registry overrides,
  when interpreter bridging is configured, then only the effective allowlisted
  tools are reachable inside the interpreter.
- Given code attempts to access unbridged host resources, when execution runs,
  then it fails closed with a clear interpreter capability error.

### FR-2: Preserve registry-authoritative tool invocation

Interpreter programmatic tool calls MUST use the same callable registry authority
as normal runtime tool execution.

Acceptance criteria:

- Given interpreter code calls `tools.read_file(...)`, when `read_file` is
  allowlisted and registered, then invocation routes through the runtime
  registry.
- Given interpreter code calls an unregistered or disabled tool, when execution
  runs, then execution fails before any host action occurs.
- Given per-node tool overrides restrict a tool, when interpreter code
  attempts to call it, then the restriction is enforced.

### FR-3: Provide runtime controls

Interpreter execution MUST be bounded and observable.

Acceptance criteria:

- Given a configured timeout, when interpreter code exceeds it, then execution
  stops and reports a clear timeout error.
- Given a maximum programmatic tool-call count, when code exceeds it, then
  execution fails closed.
- Given a maximum result size or console-output size, when code exceeds it, then
  the runtime truncates only under explicit policy or fails clearly.
- Given interpreter state snapshotting is enabled, when state is preserved, then
  only JSON-serializable data is snapshotted; live tool handles and host resources
  are never persisted.

### FR-4: Integrate with tracing and validation

Interpreter execution MUST fit the package-owned trace and validation model.

Acceptance criteria:

- Given tracing is enabled, when interpreter code runs, then trace events record
  interpreter start, completion, error, bridged tool calls, result size, and any
  captured console output or redacted code metadata.
- Given an `llm_step` has an output contract, when interpreter middleware returns
  the node output, then the output is validated through the existing
  output-contract path before becoming trusted state.
- Given token budgeting is enabled, when interpreter middleware changes prompt or
  model-call shape, then token estimates still record relevant model messages and
  can be compared against non-interpreter execution.

### FR-5: Stay optional and dependency-scoped

Interpreter support MUST be opt-in and must not add a required runtime dependency
until a candidate is selected through a separate decision.

Acceptance criteria:

- Given no interpreter configuration is present, when workflows execute, then
  current behavior remains unchanged.
- Given interpreter configuration is present but the selected backend is not
  installed, when execution is prepared, then the error names the missing optional
  dependency.
- Given tests run without live model calls, then interpreter behavior can be
  tested with fake model clients and fake registered tools.

### FR-6: Allow callers to register custom interpreters

The runtime MUST allow callers to provide custom interpreter adapters without
editing generated agent-design artifacts or adding hard-coded backend dependencies.

Acceptance criteria:

- Given a caller registers an interpreter adapter with id `custom_js`, when an
  `llm_step` references `interpreter_id: custom_js`, then execution uses that
  registered adapter.
- Given a node references an interpreter id that is only present as manifest
  metadata but has no registered adapter, when workflow preparation runs, then the
  runtime fails closed with a clear missing-interpreter error.
- Given multiple interpreter adapters are registered, when different `llm_step`
  nodes reference different ids, then each node uses only its configured
  interpreter.
- Given a caller disables or overrides an interpreter at runtime, when workflow
  preparation runs, then effective interpreter availability reflects the override
  without mutating generated artifacts.

### FR-7: Attach interpreters only to eligible `llm_step` nodes

Interpreter attachment MUST be scoped to `llm_step` nodes unless a later format
version explicitly extends support to other node kinds.

Acceptance criteria:

- Given an interpreter config targets an `llm_step`, when validation runs,
  then the attachment is accepted if the interpreter id, limits, and tool
  allowlist are valid.
- Given an interpreter config targets a `tool_use_step` or `decision_step`, when
  validation runs, then the runtime rejects the attachment as unsupported.
- Given a node-level interpreter `tool_allowlist` includes tools not effectively
  exposed to that node, when validation runs, then the runtime fails closed.
- Given interpreter config omits `interpreter_id`, when `enabled: true`,
  then the runtime either uses an explicitly configured caller default or
  fails clearly; it must not silently select a backend.

### FR-8: Keep interpreter metadata separate from executable adapters

Manifest-declared interpreter metadata MUST NOT be sufficient to execute code.
Executable interpreter adapters must come from caller registration or another
approved runtime source.

Acceptance criteria:

- Given a manifest declares an `interpreters` section, when no interpreter registry
  is supplied, then the metadata is preserved for validation/reporting but no code
  execution is possible.
- Given a registered adapter's metadata conflicts with the manifest declaration,
  when workflow preparation runs, then the runtime reports the conflict or applies
  an explicit caller override policy.
- Given interpreter metadata declares unsupported safety or side-effect policy
  values, when loading or validation runs, then the runtime fails clearly.

## Candidate Interpreter Approaches

No candidate is selected yet. The following candidates should be investigated
behind the same conceptual interface.

### Candidate A: QuickJS via Python binding

Examples to investigate include `langchain-quickjs` / `quickjs-rs`,
`quickjs`,
`quickjs-py`, or another maintained QuickJS Python binding available for Python
`>=3.11,<3.14` in the configured package indexes. The local Deep Agents checkout
uses `langchain-quickjs>=0.1.2,<0.2.0` as its optional QuickJS integration and
therefore provides a concrete reference implementation to study.

Potential strengths:

- Matches the interpreter model described in the source note.
- JavaScript/TypeScript-like code is familiar to LLMs.
- Small embedded runtime with no default filesystem, network, or shell.
- Natural syntax for `tools.<name>(...)` bridge APIs.

Risks and questions:

- Async bridge support may vary by binding; Deep Agents' PTC model exposes
  allowlisted tools as async `tools.<camelCaseName>(...)` functions, which
  should
  be studied before designing this runner's bridge.
- Need to verify dependency availability in this repository's configured package
  indexes, not only in the local Deep Agents lockfiles.
- Need hard limits for execution time, memory, recursion, result size, and
  console output.
- Need clear serialization rules for tool inputs, outputs, and state snapshots.

### Candidate B: Duktape-style JavaScript binding

Potential strengths:

- Small embeddable JavaScript runtime model.
- Potentially simpler than a full Node/V8 subprocess.
- Can expose a deliberately narrow host API.

Risks and questions:

- Package maintenance and modern Python compatibility may be weak.
- Modern JavaScript feature support may be limited.
- Async or promise-style tool-call ergonomics may be poor.

### Candidate C: WebAssembly runtime with a small guest ABI

Examples to investigate include `wasmtime` or `wasmer`.

Potential strengths:

- Stronger isolation story than many embedded interpreters.
- Explicit imports map naturally to bridged tools.
- Some runtimes support fuel, epoch, or timeout controls.
- Language-neutral in principle.

Risks and questions:

- Much higher implementation complexity.
- LLMs would not naturally write raw WASM; this would need a higher-level
  language/compiler path or prebuilt helper module.
- Poor fit for quick agent-authored loop code unless paired with more tooling.

### Candidate D: Restricted Python expression or AST interpreter

Examples to investigate include a custom `ast` evaluator, `asteval`, or
`RestrictedPython`.

Potential strengths:

- Python-native integration with the current package.
- Easy synchronous bridging to existing registry functions.
- No JavaScript dependency.
- LLMs are also strong at Python.

Risks and questions:

- Python sandboxing is difficult and easy to get wrong.
- The allowed subset must be intentionally small and audited.
- If the subset grows too broad, it risks becoming an unsafe host sandbox.

### Candidate E: Purpose-built mini DSL for programmatic tool composition

Example shape:

```yaml
steps:
  - call: search_files
    as: matches
    with:
      path: src
      regex: "class .*Registry"
  - map: matches
    call: read_file
    as: files
  - return:
      top: files
```

Potential strengths:

- Safest and easiest to validate.
- Strong fit with the existing manifest-driven architecture.
- Deterministic, traceable, and easy to test.
- Avoids general-purpose code execution.

Risks and questions:

- Less expressive than a real interpreter.
- Requires excellent examples for model reliability.
- Could duplicate graph/node semantics instead of simplifying runtime behavior.

### Candidate F: Tightly constrained subprocess runtime

Examples include a `node` subprocess with a generated harness or a Python
subprocess with strong process-level constraints.

Potential strengths:

- Mature language runtimes.
- Async and library behavior are easier to support.
- Process-level timeout and output capture are straightforward.

Risks and questions:

- Much closer to full sandboxing than the desired embedded interpreter model.
- Broader attack surface and provisioning overhead.
- Harder to make portable and safe by default.
- Risks conflicting with the requirement that interpreter support not inherit a
  whole host environment.

## Non-Functional Requirements

- Interpreter support should be optional and disabled by default.
- Interpreter backends should be caller-registered through a package-owned
  interface; manifest metadata alone must not execute code.
- Interpreter execution should be deterministic enough to test with fake clients
  and fake tools.
- Candidate dependencies must support Python `>=3.11,<3.14`.
- Candidate dependencies must be evaluated for availability in this repository's
  package indexes before being added.
- The implementation must not weaken the OpenAI adapter boundary or introduce
  multi-provider routing.
- The implementation must preserve the small primitive node taxonomy unless a
  later format-version decision explicitly changes it.
- The implementation must preserve generated artifacts as immutable baselines;
  runtime behavior can be effective/derived without mutating loaded artifacts.

## Out of Scope

- Choosing the interpreter backend.
- Requiring a built-in interpreter backend when callers can supply a custom
  adapter through the future interface.
- Implementing interpreter middleware.
- Adding new runtime dependencies.
- Adding general filesystem, network, shell, or package-install capabilities.
- Replacing `tool_use_step` nodes globally.
- Replacing the existing OpenAI adapter or tool registry architecture.
- Supporting arbitrary `SKILL.md` source loading as interpreter context.

## Safety Lessons from the Local Deep Agents Reference

The local Deep Agents checkout suggests several safety lessons that should be
carried into this repository's design evaluation:

- Treat programmatic tool calling as a privilege boundary because it may bypass
  approval or interruption hooks that normal model-mediated tool paths enforce.
- Prefer a conservative read-only preset for safe interpreter tool access.
- Require explicit acknowledgement before exposing all host tools or any tool with
  write, shell, network, subagent, or external mutation behavior.
- Exclude the interpreter/eval tool from the PTC namespace to prevent
  pointless or dangerous recursion.
- Carry max call count, timeout, memory, result-size, console-output, and snapshot
  limits in the first-class config model rather than as hidden backend defaults.
- Treat Deep Agents' `langchain-quickjs` implementation as supporting
  evidence and an example to study, not as an automatic dependency choice.

## Benchmark and Evaluation Plan

Before selecting a backend, prototype two or three candidates behind a common
interface and compare them with current serial execution.

Recommended benchmark fixtures:

1. Repeated local workspace search/read tool calls.
2. Batch document filtering with compact evidence return.
3. Fan-out/fan-in summarization over multiple tool results.
4. Route decision based on compact structured evidence.
5. Failure cases: timeout, bad code, oversized output, unavailable tool, malformed
   tool output, and output-contract failure.

Metrics to record:

- model calls avoided
- estimated prompt tokens using `token_budget.py`
- wall-clock time
- interpreter/tool-call count
- trace readability
- error quality and debuggability
- dependency size and package availability
- safety boundary confidence

## Open Questions

- NEEDS CLARIFICATION: Should interpreter output become the `llm_step` output, or
  should the interpreter be available as a model-call tool whose final result the
  model then summarizes?
- NEEDS CLARIFICATION: Should interpreter state persist only within a node, across
  nodes in a workflow, or across conversation turns when explicitly snapshotted?
- NEEDS CLARIFICATION: What language should be preferred for initial prototypes:
  JavaScript, Python subset, DSL, or multiple side-by-side experiments?
- NEEDS CLARIFICATION: Should the public interface support both synchronous and
  asynchronous interpreter adapters in the first version, or standardize on one
  calling convention?
- NEEDS CLARIFICATION: Should interpreter metadata live in a top-level manifest
  `interpreters` section, a separate `interpreter-index.yaml`, runtime overrides,
  or all three?
- NEEDS CLARIFICATION: What minimum safety controls are required before any
  general-purpose code runtime can be accepted?
- NEEDS CLARIFICATION: How should async programmatic tool calling be represented
  if the selected interpreter backend is synchronous?
- NEEDS CLARIFICATION: What redaction policy should apply to interpreter code,
  console output, bridged tool arguments, and intermediate state?

## Suggested Next Steps

- [ ] Add this feature to the deferred follow-up list in
      `specs/dynamic-agent-runner/tasks.md` if the team wants it tracked with the
      main runtime roadmap.
- [ ] Summarize any implementation details borrowed from the local Deep Agents
      checkout into repository-local artifacts so the future workflow remains
      portable.
- [x] Define initial custom-interpreter interface expectations at spec level.
- [ ] Refine a small common interpreter interface for experiments without
      adding a runtime dependency.
- [ ] Prototype QuickJS-style JavaScript, restricted Python/AST, and mini-DSL
      candidates as custom adapters against fake registry tools.
- [ ] Run benchmark fixtures and compare against current serial `llm_step` /
      `tool_use_step` execution.
- [ ] Update this spec with benchmark evidence before choosing a backend.

## Validation Checklist

- [x] Current interpreter analysis captured as a durable future feature spec.
- [x] Candidate interpreters proposed without choosing one.
- [x] Existing runtime boundaries and integration constraints recorded.
- [x] Local Deep Agents checkout inspected for supporting QuickJS/PTC evidence.
- [x] Custom interpreter registration and per-`llm_step` attachment requirements
      added at spec level.
- [ ] Candidate dependency availability checked in this repository's configured
      package indexes.
- [ ] Prototype benchmark fixtures created.
- [ ] Backend selection decision recorded after evidence is gathered.
