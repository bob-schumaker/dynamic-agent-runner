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
  - `specs/approval-interruption-resume/spec.md`
  - `specs/apple-foundation-model-adapter/spec.md`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/models.py`
  - `src/dynamic_agent_runner/registry.py`
  - `src/dynamic_agent_runner/openai_client.py`
  - `pyproject.toml`
  - local supporting checkout: `/Users/roschuma/Repos/github/deepagents/`
  - upstream repository: `https://github.com/langchain-ai/deepagents.git`
  - `https://www.marktechpost.com/2026/06/26/build-a-nanobot-style-ai-agent-in-google-colab-with-tool-calling-session-memory-skills-and-mcp-servers/`
    and its linked tutorial notebook

## References

- `specs/llm-step-interpreter-middleware/references/give-your-agents-an-interpreter.md`
  — supporting; use as the packaged source note that motivated this future
  feature evaluation
- `https://github.com/langchain-ai/deepagents.git` — supporting provenance;
  use as upstream context for the local Deep Agents checkout observations
- `https://www.marktechpost.com/2026/06/26/build-a-nanobot-style-ai-agent-in-google-colab-with-tool-calling-session-memory-skills-and-mcp-servers/`
  — supporting educational reference for provider, tool, hook, skill, session,
  and in-process MCP-adapter boundaries; not an interpreter implementation
  authority

## Objective

Evaluate and later prototype an optional interpreter middleware capability
for `llm_step` nodes so dynamic-agent workflows can reduce model-mediated round
trips,
keep intermediate working state out of model prompt history, and compose
allowlisted tool calls programmatically without exposing a full host sandbox.

This specification records the future feature idea only. It does **not**
choose an interpreter implementation and does **not** authorize implementation
yet.

Council roadmap note: keep this lower priority than the first approval/sandbox
live-action slice and the capability/status report. Interpreter middleware can be
useful, but it should remain prototype- and benchmark-driven until the package
can clearly report what bridged tools are live, approved, sandboxed, and
observable.

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

## MarkTechPost Nanobot-Style Reference Observations

The evaluated MarkTechPost tutorial reconstructs a small provider-agnostic agent
loop with normalized tool calls, a callable-to-tool decorator, session-keyed
history, lifecycle hooks, a compact skill descriptor, and an in-process
`MCPServer` facade. It is useful as evidence that small declarative capability
objects can improve caller ergonomics, but its executable behavior is not a
template for this feature:

- Loading a tutorial skill mutates one bot-wide system prompt and tool registry.
  Interpreter descriptors in DAR remain run- and node-scoped overlays and may
  not mutate global prompt or registry state.
- The tutorial's pre-tool hook observes calls, but execution still dispatches
  directly from the model response to the tool registry. DAR must use its owned
  invocation coordinator as the enforceable approval and policy boundary.
- The tutorial's MCP-named object is an in-process adapter over Python callables,
  not an MCP transport or discovery implementation. Interpreter tool bridging
  must not claim MCP semantics merely because it wraps an external-looking
  callable.
- The tutorial declares streaming hook methods without implementing a streaming
  provider path. Future interpreter lifecycle events must be tied to executable,
  testable runtime transitions rather than descriptor-only callbacks.
- The tutorial's unrestricted Python execution example is specifically rejected
  as a sandbox or interpreter design. Candidate backends remain capability-denied
  by default and bounded by timeout, memory, call-count, and result limits.

The adopted lesson is therefore declarative description plus explicit runtime
activation—not global mutation, hook-based authorization, pseudo-MCP naming, or
in-process `exec` as isolation.

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
- The current model-tool loop in `src/dynamic_agent_runner/executor.py` applies
  exposure checks, approval interruption, lifecycle hooks, tracing, registry
  invocation, state storage, and result shaping around model-originated calls.
  Interpreter support must reuse or extract that behavior into a shared
  coordinator rather than call the registry directly.
- `specs/apple-foundation-model-adapter/spec.md` requires the same DAR-owned tool
  invocation coordinator for provider callbacks. The two features should share
  one behavior boundary instead of creating separate approval stacks.
- `specs/dynamic-agent-runner/spec.md` favors package-owned interfaces,
  OpenAI-first model execution, explicit tool registries, fail-closed safety, and
  optional dependencies only behind scoped requirements.

The likely integration point is optional middleware/configuration for `llm_step`,
not a new primitive node kind in the first design.

## Proposed Capability Shape

A future manifest extension attaches one or more allowed interpreters to a
specific `llm_step` by referencing interpreter ids from a caller-provided
interpreter registry and optional manifest-declared descriptive metadata:

```yaml
interpreters:
  - id: quickjs_experimental
    label: QuickJS Experimental Interpreter
    language: javascript
    summary: Run bounded JavaScript over tools exposed to the active node.
    usage_source: interpreter-bundle/quickjs_experimental/INTERPRETER.md
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
      mode: gateway_tool
      allowed_interpreters:
        - quickjs_experimental
        - caller_analysis_dsl
      tool_allowlist:
        - search_files
        - read_file
      limits:
        max_tool_calls: 10
```

The manifest-level `interpreters` section and any `INTERPRETER.md` document are
metadata and policy only. Neither makes an interpreter executable. A
caller-provided `InterpreterRegistry`, or another separately approved runtime
source, must provide the executable adapter for every allowed interpreter id.

### Model-facing gateway tool

The first implementation should expose one stable package-owned model tool named
`run_interpreter`, rather than generating one model tool per interpreter. Its
request shape is conceptually:

```text
run_interpreter(
    interpreter_id: enum[effective allowed interpreter ids],
    program: string,
    input: object | null,
)
```

The gateway tool description includes a bounded catalog of the effective
interpreters available to the active node. Each catalog entry contains only the
id, label, language, summary, intended uses, excluded uses, invocation guidance,
and conservative capabilities needed by the model to choose and use the
interpreter. The `interpreter_id` schema enum must contain only registered,
enabled, node-allowed interpreters.

The single gateway keeps the model contract stable as callers add custom
interpreters, avoids model-tool naming collisions, and prevents tool-descriptor
growth from scaling linearly with the number of interpreters. Generating one
tool per interpreter remains a rejected first-release alternative because it
would widen the model surface and complicate caller-defined backends.

The gateway is exposed only when interpreter middleware is enabled for the node,
at least one allowed id resolves to a registered adapter, and the active model
path supports tool calls. It participates in the existing bounded model-tool
loop. The gateway must not be exposed inside an interpreter's bridged tool
namespace, preventing recursive `run_interpreter` calls.

The first implementation returns the interpreter result to the model as a tool
result so the model can synthesize the final `llm_step` response. Treating the
interpreter result directly as the node output is deferred until a separate
execution mode defines output authority and validation behavior.

### Interpreter usage descriptors

Interpreter usage guidance may be supplied programmatically by the caller or by
a package-local `interpreter-bundle/<id>/INTERPRETER.md` document. A packaged
document uses bounded Markdown with non-executable frontmatter such as:

```markdown
---
id: quickjs_experimental
label: JavaScript workspace interpreter
language: javascript
summary: Run bounded JavaScript over exposed DAR tools.
best_for:
  - filtering and aggregating tool results
  - bounded loops over workspace searches
avoid_for:
  - shell commands
  - network access
supports:
  async_tools: true
  snapshots: false
---

Use `tools.<tool_id>(arguments)` to invoke tools exposed to this node.
Return one JSON-compatible final value.
```

Descriptor loading must be opt-in, package-local, path-normalized, symlink-safe,
UTF-8, size-bounded, and free of network fetching or arbitrary caller filesystem
reads. Frontmatter and body text may describe usage but may not name an import,
module, executable, command, handler, or adapter factory to load.

Model-facing descriptor text is subject to the existing tool-descriptor budget.
When the full catalog does not fit, required interpreter metadata is retained
and optional examples or prose are omitted deterministically. Descriptor
budgeting must never remove an allowed id from the tool schema while leaving it
selectable by some hidden path.

### Metadata and policy authority

Effective interpreter configuration is derived in this order:

1. Caller registration supplies the executable adapter and truthful runtime
   capabilities.
2. Package metadata supplies descriptive usage and default policy but cannot
   add capabilities that the registered adapter does not advertise.
3. Node policy narrows allowed interpreter ids, bridged tools, and limits.
4. Runtime overrides may disable or further restrict interpreters but may not
   silently widen package or node policy.

An id, language, safety classification, or capability conflict between package
metadata and caller registration fails during workflow preparation unless an
explicit, validated override policy resolves it. Generated artifacts remain
immutable; effective configuration is derived for the run.

Expected executor-level flow:

1. `_execute_llm_step(...)` detects an interpreter policy on the node or effective
   node behavior.
2. Workflow preparation resolves registered, enabled, node-allowed interpreter
   descriptors and fails closed on conflicts or missing adapters.
3. The model receives the `run_interpreter` gateway tool with the bounded
   effective descriptor catalog and allowed-id enum.
4. A model gateway call creates a constrained interpreter session through the
   selected caller-provided adapter.
5. The interpreter exposes only explicit bridged capabilities, such as
   `tools.<tool_id>(...)`, derived from node-level tool exposure and runtime
   registry overrides.
6. Every bridged tool request enters a DAR-owned tool invocation coordinator
   before registry invocation so exposure, validation, approval, lifecycle,
   tracing, state, redaction, and result-shaping behavior remains authoritative.
7. Results, retries, trace events, token accounting, and output-contract
   validation remain package-owned.
8. The interpreter result returns as a model-facing tool result and the model
   produces the authoritative `llm_step` output.

## Custom Interpreter Interface

The runner should support caller-specified custom interpreters through a
package-owned interface rather than hard-coding a single backend. This mirrors
the existing model-client and tool-registry approach: generated artifacts may
declare intent and policy, while the caller supplies executable adapters at
runtime.

The names below are illustrative future API shapes, not current exports from
`dynamic_agent_runner`.

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
            label="JavaScript workspace interpreter",
            language="javascript",
            summary="Run bounded JavaScript over exposed DAR tools.",
            side_effect="none",
            supports_snapshots=True,
        ),
        adapter=my_quickjs_adapter,
    )
)

result = run_agent_workflow(
    package_directory="path/to/agent-package",
    prompt="Analyze the workspace.",
    tool_registry=tool_registry,
    interpreter_registry=registry,
)
```

Conceptual protocol shape:

```python
class InterpreterAdapter(Protocol):
    async def create_session(
        self,
        *,
        node_id: str,
        definition: InterpreterDefinition,
        limits: InterpreterLimits,
        tool_bridge: InterpreterToolCoordinatorBridge,
        snapshot: bytes | None = None,
    ) -> InterpreterSession: ...

class InterpreterSession(Protocol):
    async def evaluate(
        self,
        request: InterpreterRequest,
    ) -> InterpreterResult: ...
    async def snapshot(self) -> bytes | None: ...
    async def close(self) -> None: ...
```

The exact type names are provisional, but the interface should preserve these
responsibilities:

- `InterpreterDefinition` records non-executable metadata: id, label, language,
  summary, usage guidance, default limits, safety classification, conservative
  capabilities, snapshot support, provenance, and raw manifest metadata.
- `RegisteredInterpreter` combines an `InterpreterDefinition` with an executable
  adapter supplied by the caller.
- `InterpreterRegistry` resolves the effective allowed interpreter set for each
  `llm_step`, applies restrictive runtime overrides, and fails closed for
  missing, conflicting, or disabled interpreters.
- `InterpreterToolCoordinatorBridge` exposes only effective allowlisted tools to
  the interpreter session and routes every request through DAR's tool invocation
  coordinator rather than directly to a handler or `ToolRegistry`.
- `InterpreterRequest` carries code or DSL content, selected execution mode, node
  id, effective prompt context, and any serializable prior state.
- `InterpreterResult` carries the final value, optional stdout/stderr, structured
  metadata, tool-call records, snapshot payload, timeout/error information, and
  result-size accounting.

Custom interpreters may be implemented by callers using QuickJS, restricted
Python, a DSL, WebAssembly, a subprocess harness, or another backend, but the
runner should interact with them only through this package-owned interface.
The initial public interface is async-first. A caller may wrap a synchronous
backend behind its adapter, but DAR does not expose a second synchronous
interpreter protocol in the first release.

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

### FR-2: Preserve DAR-managed tool invocation

Interpreter programmatic tool calls MUST enter the same DAR behavior stack as
normal model-originated tool calls before reaching the callable registry.

Acceptance criteria:

- Given interpreter code calls `tools.read_file(...)`, when `read_file` is
  allowlisted and registered, then invocation routes through a DAR-owned
  coordinator that applies exposure, argument validation, approval policy,
  lifecycle hooks, tracing, registry invocation, workflow-state storage,
  redaction, and model-facing result shaping.
- Given interpreter code calls an unregistered or disabled tool, when execution
  runs, then execution fails before any host action occurs.
- Given per-node tool overrides restrict a tool, when interpreter code
  attempts to call it, then the restriction is enforced.
- Given a bridged tool requires approval, when no approval decision exists, then
  the handler and registry invocation do not run. The coordinator either awaits
  an approved in-process resolver or returns DAR's interruption behavior.
- Given approval is denied, cancelled, expired, or unresolved, then the handler
  is not invoked and the interpreter receives only a DAR-controlled failure or
  interruption representation.
- Given the registry returns a `ToolResult`, then the interpreter receives only
  the serialized `model_facing_output`; DAR retains the complete result and
  trace/state authority.

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
  model-call shape, then token estimates include the gateway descriptor and
  effective interpreter catalog and can be compared against non-interpreter
  execution.

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
  `llm_step` includes `custom_js` in `allowed_interpreters` and the model selects
  it through `run_interpreter`, then execution uses that registered adapter.
- Given a node references an interpreter id that is only present as manifest
  metadata but has no registered adapter, when workflow preparation runs, then the
  runtime fails closed with a clear missing-interpreter error.
- Given multiple interpreter adapters are registered and allowed for one
  `llm_step`, when its gateway schema is prepared, then the model sees only those
  effective ids and may select among them explicitly.
- Given different `llm_step` nodes allow different interpreter sets, when each
  node is prepared, then its gateway catalog and enum contain only its effective
  set.
- Given a caller disables or overrides an interpreter at runtime, when workflow
  preparation runs, then effective interpreter availability reflects the override
  without mutating generated artifacts.

### FR-7: Attach interpreters only to eligible `llm_step` nodes

Interpreter attachment MUST be scoped to `llm_step` nodes unless a later format
version explicitly extends support to other node kinds.

Acceptance criteria:

- Given an interpreter config targets an `llm_step`, when validation runs,
  then the attachment is accepted if `allowed_interpreters`, limits, and tool
  allowlist are valid.
- Given an interpreter config targets a `tool_use_step` or `decision_step`, when
  validation runs, then the runtime rejects the attachment as unsupported.
- Given a node-level interpreter `tool_allowlist` includes tools not effectively
  exposed to that node, when validation runs, then the runtime fails closed.
- Given interpreter config enables the gateway with an empty effective
  `allowed_interpreters` set, then preparation fails clearly; it must not select
  a caller default or unrelated registered backend silently.

### FR-8: Keep interpreter metadata separate from executable adapters

Manifest-declared interpreter metadata MUST NOT be sufficient to execute code.
Executable interpreter adapters must come from caller registration or another
approved runtime source.

Acceptance criteria:

- Given a manifest declares an `interpreters` section, when no interpreter registry
  is supplied, then the metadata is preserved for validation/reporting but no code
  execution is possible.
- Given a registered adapter's metadata conflicts with the manifest declaration,
  when workflow preparation runs, then the runtime fails or applies an explicit
  validated override policy; it must not merge contradictory capabilities.
- Given interpreter metadata declares unsupported safety or side-effect policy
  values, when loading or validation runs, then the runtime fails clearly.

### FR-9: Expose a stable model-facing gateway

The first release MUST expose interpreter execution through one DAR-owned model
tool and return its result to the model tool loop.

Acceptance criteria:

- Given interpreter middleware is enabled with at least one effective
  interpreter, when the model request is built, then it includes one
  `run_interpreter` tool whose `interpreter_id` enum contains only effective ids.
- Given no effective interpreter is available, when request preparation runs,
  then the gateway is omitted for disabled middleware or preparation fails for
  explicitly required middleware.
- Given the model selects an id outside the enum, when DAR validates the call,
  then no interpreter session is created.
- Given an interpreter completes successfully, when its gateway result returns,
  then the result enters the model transcript as structured tool output and the
  model remains responsible for the final `llm_step` response.
- Given the active model adapter cannot support the gateway tool call, when
  capability validation runs, then execution fails before model dispatch.
- Given a bridged tool namespace is constructed, then `run_interpreter` and any
  equivalent interpreter-evaluation tool are excluded to prevent recursion.

### FR-10: Provide bounded usage descriptions

The runtime MUST provide enough interpreter-specific guidance for model
selection without treating descriptive content as executable configuration.

Acceptance criteria:

- Given multiple interpreters are effective for a node, when the gateway
  description is rendered, then each has a stable id, language, concise summary,
  intended uses, excluded uses, and invocation guidance.
- Given a package-local `INTERPRETER.md` is configured, when it is loaded, then
  path containment, symlink safety, UTF-8 decoding, size, and frontmatter schema
  are validated before its content reaches the model.
- Given a descriptor attempts to name executable loading behavior, when
  validation runs, then it is rejected as non-descriptive configuration.
- Given descriptor content exceeds the active budget, when the catalog is
  rendered, then optional prose is reduced deterministically while identity,
  language, safety, and invocation essentials remain.
- Given a caller supplies an executable adapter without package usage metadata,
  when its registered definition contains valid bounded usage guidance, then it
  may still participate without modifying generated workflow artifacts.

## Candidate Interpreter Approaches

No candidate is selected yet. The following candidates should be investigated
behind the same conceptual interface.

### Candidate A: QuickJS via Python binding

Examples to investigate include `langchain-quickjs` / `quickjs-rs`,
`quickjs`,
`quickjs-py`, or another maintained QuickJS Python binding available for the
repository's supported Python range, including its selected Python 3.14 runtime,
in the configured package indexes. The local Deep Agents checkout uses
`langchain-quickjs>=0.1.2,<0.2.0` as its optional QuickJS integration and
therefore provides a concrete reference implementation to study.

Potential strengths:

- Matches the interpreter model described in the source note.
- JavaScript/TypeScript-like code is familiar to LLMs.
- Small embedded runtime with no default filesystem, network, or shell.
- Natural syntax for `tools.<name>(...)` bridge APIs.

Risks and questions:

- Async bridge support may vary by binding; Deep Agents' PTC model exposes
  allowlisted tools as async `tools.<camelCaseName>(...)` functions, which
  should be studied before designing this runner's bridge.
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
- Interpreter usage descriptors should be non-executable, bounded, and derived
  only from package-local or caller-supplied content.
- The model-facing surface should remain one stable gateway tool regardless of
  how many custom interpreters a caller registers.
- Interpreter execution should be deterministic enough to test with fake clients
  and fake tools.
- Candidate dependencies must support the repository's configured Python range,
  including its selected Python 3.14 runtime.
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
- Loading interpreter adapters, modules, commands, or factories from descriptor
  frontmatter.
- Reading interpreter usage documents from arbitrary external paths or network
  locations.
- Treating the first-release interpreter result as authoritative node output
  without a final model response.

## Safety Lessons from the Local Deep Agents Reference

The local Deep Agents checkout suggests several safety lessons that should be
carried into this repository's design evaluation:

- Treat programmatic tool calling as a privilege boundary because it may bypass
  approval or interruption hooks that normal model-mediated tool paths enforce.
- Never give an interpreter adapter a raw handler or unrestricted registry
  reference. Give it only a run- and node-scoped coordinator bridge.
- Prefer a conservative read-only preset for safe interpreter tool access.
- Require explicit acknowledgement before exposing all host tools or any tool with
  write, shell, network, subagent, or external mutation behavior.
- Exclude the interpreter/eval tool from the PTC namespace to prevent
  pointless or dangerous recursion.
- Carry max call count, timeout, memory, result-size, console-output, and snapshot
  limits in the first-class config model rather than as hidden backend defaults.
- Treat Deep Agents' `langchain-quickjs` implementation as supporting
  evidence and an example to study, not as an automatic dependency choice.

## Resolved Design Decisions

1. The model-facing surface is one DAR-owned `run_interpreter` gateway tool, not
   one generated tool per interpreter.
2. The gateway returns interpreter output to the model tool loop; the model's
   subsequent response remains the authoritative `llm_step` output.
3. One node may allow multiple explicit interpreter ids, and the model selects
   an id from the gateway schema enum.
4. Executable adapters are supplied through a caller-provided
   `InterpreterRegistry`; package metadata and `INTERPRETER.md` files remain
   descriptive and non-executable.
5. The initial adapter interface is async-first. Callers may wrap synchronous
   backends without creating a second DAR protocol.
6. Interpreter mutable state is scoped to one node execution in the first
   release. Cross-node, cross-turn, or durable snapshots require a later slice.
7. Interpreter-originated tool requests pass through a DAR-owned invocation
   coordinator before registry invocation, preserving approval and runtime
   behaviors.
8. Package, node, and runtime policy may narrow caller-registered capabilities
   but may not silently widen them.
9. Compact capability objects may inform descriptor ergonomics, but skill
   loading, process-global prompt mutation, and process-global tool registration
   are not interpreter activation mechanisms.

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

- NEEDS CLARIFICATION: What language should be preferred for initial prototypes:
  JavaScript, Python subset, DSL, or multiple side-by-side experiments?
- NEEDS CLARIFICATION: What minimum safety controls are required before any
  general-purpose code runtime can be accepted?
- NEEDS CLARIFICATION: What redaction policy should apply to interpreter code,
  console output, bridged tool arguments, and intermediate state?
- NEEDS CLARIFICATION: Should approval-required nested tool calls be limited to
  hosts with an in-process resolver in the first release, or may the interpreter
  session snapshot and exit through DAR interruption for later resume?
- NEEDS CLARIFICATION: What maximum descriptor budget and per-interpreter usage
  limit should the first release enforce?

## Suggested Next Steps

- [x] Add this feature to the deferred follow-up list in
      `specs/dynamic-agent-runner/tasks.md` if the team wants it tracked with the
      main runtime roadmap.
- [ ] Summarize any implementation details borrowed from the local Deep Agents
      checkout into repository-local artifacts so the future workflow remains
      portable.
- [x] Define initial custom-interpreter interface expectations at spec level.
- [x] Refine a small common interpreter interface for experiments without
      adding a runtime dependency.
- [x] Define the stable model-facing gateway, multi-interpreter catalog, and
      non-executable descriptor boundary.
- [ ] Specify or reuse a DAR-owned tool invocation coordinator that can preserve
      approval, hooks, tracing, state, and result shaping for nested interpreter
      calls.
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
- [x] Multiple node-allowed interpreters and caller-provided adapters are covered.
- [x] Frontmatter and usage descriptions are non-executable and bounded.
- [x] Gateway tool exposure and final model synthesis behavior are defined.
- [x] Nested tool calls are required to enter DAR approval and tool-runtime
      behavior before registry invocation.
- [x] The MarkTechPost nanobot-style tutorial is recorded as supporting evidence,
      with global mutation, hook-based authorization, pseudo-MCP naming, and
      unrestricted Python execution explicitly rejected.
- [ ] Candidate dependency availability checked in this repository's configured
      package indexes.
- [ ] Prototype benchmark fixtures created.
- [ ] Backend selection decision recorded after evidence is gathered.
