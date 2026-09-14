# MLX Local-Model Tool-Use Specification

## Metadata

- Feature slug: `mlx-local-model-tool-use`
- Mode: guided
- Artifact type: authoritative SDD follow-up specification
- Status: delivered
- Parent feature: `specs/mlx-local-model-adapter/spec.md`
- Related feature specs:
  - `specs/model-interface-parity/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/tool-invocation-coordinator/spec.md`

## Objective

Make an explicitly configured, in-process MLX backend capable of producing
DAR-normalized tool calls while preserving DAR as the only owner of tool
selection validation, schema validation, approval, invocation, lifecycle,
tracing, and result continuation.

## Problem Statement

The completed MLX adapter is deliberately text-only. It rejects
`OpenAIModelRequest.tools`, renders a plain prompt, and returns only
`ModelResponse(content=...)`. Removing that rejection would not create a tool
contract: the current `mlx_lm` backend has no declared renderer or parser for
tool descriptors, assistant tool calls, or tool results.

MLX needs a small adapter-owned seam that can accept a selected model family's
native template and response syntax, but emits only DAR's strict
`ModelResponse(tool_calls=...)` contract. It must not add another agent loop or
make a generic assumption about every `mlx-lm` tokenizer.

## Scope

This follow-up covers:

1. a caller-injected, versioned `MLXToolCodec` contract for rendering tool-aware
   prompts and parsing model output;
2. adapter gating that enables tool calling only for an explicitly compatible
   codec/backend pair;
3. bounded normalization of a codec's candidate into `ModelToolCall`;
4. transcript rendering for DAR's existing assistant-tool-call and
   `model_tool_result` continuation messages; and
5. deterministic fake-only tests for the codec, sync/async adapter behavior,
   and the existing executor loop.
6. structural recognition of native MLX safetensors snapshots for local
   resolution, availability, and scoped inventory.
7. an opt-in, package-owned Qwen3 MLX codec/backend helper for the pinned
   Qwen3 Instruct artifact.

## Non-Goals

- No MLX server, OpenAI-compatible endpoint, process lifecycle, or scheduler.
- No executor branch, second tool loop, direct handler invocation, approval
  policy, trace policy, or tool-schema policy.
- No tool support for arbitrary `mlx-lm` models or tokenizers. M6.4 may enable
  the selected pinned Qwen3 Instruct pair only after its compatible
  codec/template/parser implementation passes the runtime gate; every other
  stock `_MLXLMBackend` use remains text-only.
- No live MLX model, Metal, Hugging Face, network, or external-tool call in
  pytest.
- No multi-call/parallel-call support in the first codec slice.
- No structured-output, streaming, embeddings, multimodal, or model-conversion
  expansion.
- No tensor-header inspection, tokenizer/template compatibility claim, model
  load, generation, or tool-capability change from asset recognition alone.

## Authoritative Contract Decisions

### Codec and backend boundary

`MLXToolCodec` is a caller-injected, versioned protocol. It owns only two
model-family-specific translations:

- render the normalized request messages, exposed tool schemas, and tool choice
  into the selected template; and
- parse one generated model response into either ordinary text or one typed tool
  call candidate.

The adapter owns the safety envelope around that protocol. A codec is not a
tool dispatcher and receives no registry, approval, handler, credential, or
trace collaborator. A backend may advertise tool capability only when it is
paired with the configured codec; otherwise it remains text-only.

The built-in codec target is Qwen3 Instruct with its native tool-aware chat
template. The parity-suite artifact, upstream `mlx-lm` provenance, immutable
revisions, package lock hashes, and update policy are recorded in
[`implementation-decision.md`](implementation-decision.md). The implementation
must verify the selected tokenizer API at model load before advertising tool
capability. If the tokenizer/template cannot meet this contract, the backend
remains text-only rather than falling back to a generic text prompt.

The stock `_MLXLMBackend` remains unsupported until it supplies that verified
codec/template implementation. This does not block the generic injected codec
seam or its fake-only tests.

### M6.4 owned codec

T6.4.1 recorded `incompatible_parser`. The pinned Qwen3 template emits a
delimiter-wrapped `<tool_call>…</tool_call>` response, while the installed
`mlx_lm` wrapper-selected `json_tools.parse_tool_call` accepts only extracted
JSON and raises `JSONDecodeError` for that native envelope. DAR explicitly owns
the narrow envelope parser in
[`qwen3_mlx_tools.py`](../../src/dynamic_agent_runner/qwen3_mlx_tools.py) rather
than relying on that incomplete upstream parser.

`create_qwen3_mlx_local_adapter()` and
`create_qwen3_mlx_local_async_adapter()` are opt-in and require both a
caller-loaded model/tokenizer pair and `MLXLocalModelConfig.expected_model_id`
equal to the pinned artifact identity. They support only omitted DAR
`tool_choice`, one pure native envelope, and one JSON-object argument payload.
Generic MLX factories remain text-only, and no model-family-name detection,
profile registry, tool dispatch, approval behavior, or alternate artifact is
added.

The dated manual-local competency outcome is recorded in
[`validation.md`](validation.md). It qualifies only the recorded host, exact
verified model bytes, runtime, settings, and bounded recording tool; it does
not broaden the built-in capability, enable generic MLX tool use, or constitute
pytest, CI, or release evidence.

### Superseded upstream-parser-only codec-profile activation

M6.4 promotes only profiles that DAR owns and has qualified. The first profile
is the selected Qwen3 Instruct artifact. It must use `mlx_lm`'s public
tokenizer/template and generation interfaces without vendoring or copying an
upstream template or parser. The existing generic factories gain this additive
opt-in:

```python
create_mlx_local_adapter(
    config: MLXLocalModelConfig,
    *,
    backend: MLXLocalBackend | None = None,
    dependency_loader: DependencyLoaderCallable | None = None,
    platform_system: PlatformSystemCallable | None = None,
    download_file: DownloadFileCallable | None = None,
    download_snapshot: DownloadSnapshotCallable | None = None,
    tool_codec: MLXToolCodec | None = None,
    enable_builtin_codecs: bool = False,
) -> MLXLocalModelAdapter

create_mlx_local_async_adapter(
    config: MLXLocalModelConfig,
    *,
    backend: MLXLocalBackend | None = None,
    dependency_loader: DependencyLoaderCallable | None = None,
    platform_system: PlatformSystemCallable | None = None,
    download_file: DownloadFileCallable | None = None,
    download_snapshot: DownloadSnapshotCallable | None = None,
    tool_codec: MLXToolCodec | None = None,
    enable_builtin_codecs: bool = False,
) -> AsyncMLXLocalModelAdapter
```

`enable_builtin_codecs` defaults to `False`, preserving existing text-only
behavior. When it is `True`, the factory performs a local, no-network profile
selection and preflight at construction. An exact qualified profile configures
the built-in codec and may report `tool_calling=True`; an absent, mismatched, or
incompatible profile returns the normal text-only adapter without a fallback
prompt or parser. Capability access itself remains side-effect free.

Caller-supplied `tool_codec` and compatible `backend` remain the explicit
extension seam for models DAR does not natively support. The factory must not
select a built-in profile when a caller supplies either. That caller-owned path
still requires the existing compatible codec/backend pair before it can report
tool capability. DAR must not expose a public profile-registration API or use a
model-family name as evidence of compatibility.

Preflight admits only an exact default-Hub snapshot for the model repository and
immutable revision in a checked-in qualified profile. The profile names
that snapshot with a canonical Hub-relative locator; preflight joins it to the
caller-selected or default cache root, then verifies containment and the
checked-in manifest of config, tokenizer, and weight filenames with their
SHA-256 digests. An explicit local directory, a lookalike model ID, a different
snapshot revision, or a mutable alias is ineligible for the built-in path. The
preflight must verify all of the following before it advertises or attempts tool
calling:

1. the resolved model identity and immutable artifact revision match the
   implementation decision;
2. the tokenizer exposes a native chat-template API that can render the full
   DAR transcript with supplied tools and a generation prompt;
3. the selected template explicitly supports assistant tool calls and matching
   tool-result continuation messages; and
4. the selected `mlx-lm` release exposes a compatible public parser or
   structured generation result for one Qwen3 tool call.

M6.4.1 is discovery-only. It must create a dated compatibility profile naming
the public symbols and signatures used, the exact parser input/result mapping,
the supported subset of DAR `tool_choice` values, and the provenance manifest.
It must use fixed synthetic fixtures and record only structural render/result
shapes plus hashes or redacted excerpts; it must not preserve host prompts,
credentials, handler payloads, or an unredacted rendered transcript. Its only
outcomes are `qualified`, `ineligible_provenance`, `incompatible_runtime`,
`incompatible_template`, `incompatible_tool_choice`, or `incompatible_parser`.
`incompatible_runtime` covers an unavailable or wrong `mlx-lm` distribution or
public generation API. Only `qualified` unlocks T6.4.2–T6.4.6; every other
outcome closes M6.4 as text-only without a custom parser or another Qwen
artifact.

The selected built-in profile supports only the `tool_choice` values explicitly
recorded as faithfully rendered by that profile. It rejects every other value
before generation; it must not collapse `none`, `auto`, `required`, or a named
tool into a different choice. Generation is serialized by one adapter-local
lock so sync and async callers cannot interleave model generation or duplicate
a load.

Failure of any activation gate must raise the existing package-owned
unsupported/tool-execution error before a tool-bearing generation or dispatch
can occur. The gate must not download, mutate a model cache, fall back to a
generic prompt, infer a parser from model text, or enable a different Qwen
revision merely because its name is similar.

The built-in codec must use the existing `MLXToolCodec` boundary and the
adapter's existing bounded normalization. It may not gain registry, approval,
handler, trace, tool-loop, endpoint, or external-service responsibilities.

### Rendered transcript

The codec receives the complete existing `OpenAIModelRequest`: system,
developer, user, assistant, assistant tool-call, and `model_tool_result`
messages. It must render only the tools supplied on that request and preserve
message order. The codec must structurally serialize the normalized tool-call
ID, name, arguments, and matching tool result on continuation; it must not
interpolate raw handler output into an unrelated prompt string.

### Parse and normalization boundary

The codec returns either text or exactly one tool-call candidate. The adapter
must reject a response that attempts multiple calls, combines a call with
uncontracted trailing prose, uses an unavailable name, repeats a supplied call
ID, exceeds a configured bound, or cannot be parsed unambiguously.

For a call candidate, arguments must decode to a JSON object. The adapter must
reject duplicate JSON object keys, non-finite numbers, excess nesting, excess
members, and byte-limit violations before returning a `ModelResponse`. It must
serialize accepted arguments canonically (sorted keys, compact separators,
finite JSON only) and return them as the normalized `ModelToolCall.arguments`.
Registry schema validation remains the executor/coordinator's responsibility.

A codec-supplied call ID must be non-empty and unique within its response. When
the selected codec permits an omitted ID, the adapter creates a response-scoped
opaque ID from its response ID plus the call ordinal; the continuation renderer
must preserve that same ID. Duplicate supplied IDs are errors. All rejected
model output raises `ModelExecutionError` and returns zero normalized calls.

### Capability truthfulness

`tool_calling` is `False` unless both a configured codec and a backend that
declares compatibility are present. In that state, tool-bearing requests fail
closed before model generation. When both are present, the sync and async
factories report `tool_calling=True` and share the same render/parse path; the
async adapter continues to run that blocking work through `asyncio.to_thread`.

### Native MLX safetensors asset recognition

The existing converted layout remains an alternative accepted layout with its
current `config.json`, `tokenizer.model`, and `weights.npz` (or
`weights.*.npz`) behavior unchanged. Native recognition is structural only and
is owned by one non-public validator in `local_models.py`; the MLX adapter,
availability check, and scoped inventory must call it rather than reproduce
their own native checks.

A native layout has a `config.json` and `tokenizer.json`, plus native weights.
Each required artifact must resolve to a regular file within its allowed root.
For a detected Hub snapshot, the allowed root is its `models--*` repository so
standard snapshot-to-repository-blob symlinks remain valid. For another local
directory, it is the model directory itself. A required file or shard that
resolves outside that root is invalid.

Native weights are either exactly one root-level `model.safetensors` without an
index and with no matching shard files, or an index named
`model.safetensors.index.json`. Any multiweight or sharded layout requires that
index. An index is at most 1 MiB of
UTF-8 JSON, rejects duplicate object keys, and is an object with a nonempty
`weight_map` object of at most 10,000 entries. Each mapped value must be a
root-level safe filename matching `model.safetensors` or
`model-<five digits>-of-<five digits>.safetensors`; it must resolve to a regular
contained file. Repeated values are allowed because multiple tensor names may
share a shard. If an index is present, every matching root-level model-weight
file must be referenced by it. Malformed, missing, unreferenced, traversing,
absolute, non-string, or escaping entries fail closed. This deliberately does
not validate safetensors headers or tensor semantics.

Valid native and converted layouts appear as one MLX directory item in scoped
inventory. Invalid native layouts raise the existing package-owned
`LocalModelResolutionError` for adapter resolution, yield `INVALID` for
availability, and are omitted from inventory. Recognition alone never calls a
loader, imports `mlx_lm`, downloads, contacts an endpoint, or changes stock
tool capability.

## Functional Requirements

### FR-1: Explicit tool capability

- Given the stock MLX backend and no compatible codec, when a request contains
  tools, then generation fails before the backend is called and capability
  metadata reports `tool_calling=False`.
- Given a compatible injected codec/backend pair, when a request contains
  tools, then the adapter renders through that codec rather than the legacy
  plain-text prompt path.

### FR-2: Strict DAR emission

- Given a valid codec tool-call candidate, when normalization completes, then
  the adapter returns one `ModelToolCall` in `ModelResponse` and invokes no
  handler itself.
- Given malformed, oversized, duplicate, unavailable, or ambiguous candidate
  data, then the adapter raises `ModelExecutionError` before the executor can
  dispatch a tool.

### FR-3: Continuation parity

- Given the executor appends an assistant call and matching tool result, when it
  asks MLX for the next response, then the codec receives and renders those
  normalized transcript messages in order with their same call ID.
- Given that continuation response is text, then the existing executor returns
  it through its ordinary final-response path without an MLX-specific loop.

### FR-4: First-slice bounds

- The first codec supports at most one call per model response.
- Limits for generated response bytes, candidate bytes, argument bytes,
  argument nesting, and argument member count are required configuration or
  fixed documented constants; every limit has a deterministic test.
- The first codec accepts either a text response or a tool call, not both.

### FR-5: Native MLX asset admission

- Given a native safetensors directory matching the structural contract, when
  it is resolved by an injected MLX adapter, checked for availability, or found
  in a scoped default-Hub inventory, then it is admitted as one MLX asset
  without loading a model.
- Given the existing converted-NPZ layout, when the same entry points run, then
  its current accepted behavior remains unchanged.
- Given an invalid native file, index, or contained-path condition, when those
  entry points run, then resolution fails with `LocalModelResolutionError`,
  availability is `INVALID`, and inventory omits the snapshot.

## Acceptance and Validation

- Fake codec tests prove initial rendering includes only the exposed schemas and
  preserves request message order.
- Fake codec tests prove continuation rendering contains the canonical call ID,
  name, arguments, and matching `model_tool_result`.
- Parser tests cover valid text, one valid call, invalid JSON, duplicate keys,
  non-finite values, invalid root, unavailable names, duplicate IDs, multiple
  calls, trailing prose, and each bound.

### Superseded M6.4 built-in Qwen3 acceptance

- Given the pinned artifact and a compatible fake tokenizer/parser result, when
  a tool-bearing initial or continuation request reaches the built-in path,
  then the codec calls the native template API with only DAR's supplied tools,
  preserves the complete ordered transcript, and emits the existing canonical
  one-call `ModelToolCall` representation.
- Given a missing, incompatible, or unexpected tokenizer/template/parser/model
  identity, when the same request is made, then capability remains false and
  the request fails before model generation or tool dispatch.
- Given a text-only request, when the built-in runtime gate is unavailable,
  then existing text generation behavior remains unchanged.
- Given a generic MLX factory with `enable_builtin_codecs=False` or a capability
  property access, when no caller supplies a codec, then no model is loaded and
  `tool_calling=False` remains unchanged.
- Given a generic MLX factory with `enable_builtin_codecs=True`, when its
  resolved cache artifact matches one checked-in qualified profile, then it
  selects that codec; when it does not, then it remains text-only without a
  fallback parser or erroring the otherwise valid text adapter.
- Given a caller-supplied codec or backend, when `enable_builtin_codecs=True`,
  then no built-in profile is selected; only an explicit compatible pair may
  report tool capability.
- Given an exact pinned snapshot whose compatibility profile supports a subset
  of `tool_choice` values, when another choice is requested, then the adapter
  rejects it before generation or dispatch rather than coercing it.
- Given a compatible live eligible Apple Silicon host and the pinned local
  artifact, when the manual competency protocol is initiated, then it records
  the exact DAR revision, host class, artifact revision and digest, `mlx-lm`
  version, codec version, generation settings, and bounded controlled-tool
  outcomes for initial selection and continuation. This evidence is manual,
  local-only, outside pytest and CI, and does not make any claim about arbitrary
  MLX models.
- Sync and async tests prove identical normalization, capability reporting, and
  zero backend call on rejected requests.
- An executor integration test proves one fake MLX call reaches the existing
  coordinator/registry, then the second rendered request contains the result;
  malformed output invokes no handler.
- Focused tests remain fake-only and require no optional MLX import.
- Native fixtures cover direct native weights, indexed shards, the unchanged
  NPZ fixture, missing config/tokenizer/weights, malformed or duplicate-key
  indexes, non-string/traversing/missing/unreferenced shard entries, a direct
  layout with an extra shard, and
  escaping required-file or shard symlinks. They cover injected sync and async
  adapter resolution, availability, and default-Hub inventory, including a
  valid repository-contained Hub blob symlink. They assert no loader, optional
  import, download, endpoint, or process seam is called.

## Implementation Readiness

M6.1 and M6.2 delivered the codec seam under their stated gates. M6.3 delivered
the structural admission contract with fake-only adapter, availability, and
inventory tests; a structurally admitted snapshot is not evidence that the
default backend, tokenizer template, or tool codec is compatible.
