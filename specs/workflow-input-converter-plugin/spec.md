# Workflow Input Converter Plugin Specification

## Metadata

- Feature slug: `workflow-input-converter-plugin`
- Status: planned; sealed Python converter packages use the standard runner
- Owner: dynamic-agent-runner workflow-host and local-model boundaries
- Related specifications:
  - `specs/model-execution-plugin-interface/spec.md`
  - `specs/local-model-runner-interface/spec.md`
  - `specs/local-tool-sandbox-hardening/spec.md`
  - `specs/natural-language-workflow-authoring/spec.md`

## Objective

Let a workflow package carry a durable, sealed input-converter plugin that
turns one opaque incoming byte payload into the private model inputs required by
its selected runner. The workflow user supplies only a prompt and bytes; they
do not select a media format, converter, processor, model path, or tensor
shape.

The converter may be generated while authoring a workflow. It is immutable for
that registered workflow instance. DAR validates its identity and execution
contract, loads its fixed Python-package entry point through the standard
runner, and never needs format-specific knowledge such as JPEG, TIFF, GIF,
PCAP, or protobuf.

## Problem Statement

The first `transformers-peft-single-image-v1` profile embeds JPEG/PNG decode
and Qwen input packing in DAR. That does not scale: another model may require a
different decoder, conversion library, processor call, multimodal packing
scheme, or raw-binary parser. Teaching DAR each format makes the generic
runtime a growing registry of model-specific behavior.

An unrestricted `bytes_processor(bytes)` callable is not an adequate solution.
It has no durable identity, declared compatibility, capability boundary,
resource policy, or safe lifecycle. A workflow-local converter plugin provides
the same implementation freedom behind a reviewable, sealed contract.

## Scope

This feature defines:

1. a versioned, package-contained input-converter manifest and contract;
2. registration of a converter as an immutable asset of one workflow instance;
3. a private graph edge from sealed payload to a compatible standard model
   runner;
4. lifecycle, resource, and failure requirements for a sealed converter
   package; and
5. the first runner execution contract, `transformers-generate-v1`, for which a
   converter creates processor-produced generation inputs.

## Non-Goals

This feature does not:

- define a universal binary media registry, MIME taxonomy, image decoder, or
  tensor representation in DAR;
- let a workflow user provide a converter, executable path, model path, or
  arbitrary function at invocation time;
- make a converter result a workflow artifact, tool result, user-visible value,
  reusable handle, or cross-worker serialization format;
- expose converter code with caller paths, model paths, host callbacks, or
  mutable invocation-time configuration;
- make model-generated converter code trusted, portable across workflow
  instances, or automatically promotable to a host-wide plugin; or
- move output validation or domain semantics into DAR.

## Architecture

### Core invocation

The DAR-facing invocation remains deliberately small:

```text
registered workflow + prompt + sealed payload bytes
```

The workflow already selects a logical model requirement and a runner execution
contract. The host resolves those choices before execution; prompt text and
payload bytes cannot select or replace them.

### Private conversion edge

Inside the existing standard model-runner process, the execution shape is:

```text
sealed payload bytes + prompt
  -> workflow-sealed InputConverterPlugin.pack(...)
  -> opaque PackedModelInput
  -> compatible StandardModelRunner.generate(...)
  -> normalized text result
```

`PackedModelInput` is private to the converter package and the declared runner
execution contract. It can be a mapping of framework tensors for
`transformers-generate-v1`, but DAR neither inspects nor serializes it. There is
no universal tensor schema.

The converter is a private graph node. The package can declare it for
validation and trace identity, but a workflow user cannot invoke it directly
and no graph edge exposes decoded input or packed state outside the standard
runner.

### JSON output admission

The generic syntax-only response contract is exactly:

```yaml
response_format:
  type: json_object
```

It requests one JSON object, not a JSON Schema, a floorplan schema, or a
model-specific prompt rewrite. A runner may accept it only when its adapter
advertises `json_mode: true`; otherwise it must reject the request before it
loads a model or consumes sealed input. A runner that advertises `json_mode`
must constrain generation so that its returned completion is strict JSON. A
prompt instruction alone does not satisfy this capability.

An optional workflow-owned output postprocessor may run after generation and
before terminal validation. It receives the original bounded text privately and
returns strict JSON only when a declared deterministic repair policy can prove
that it did not invent a missing value, array item, object member, or closing
structure. It retains the original text, repaired text when any, their digests,
and a bounded repair report as user-only diagnostic artifacts. DAR does not
enable repair implicitly, interpret the JSON's fields, or expose either text in
traces or public API results. A failed postprocessor is a declared terminal
failure, not a retry through unconstrained generation.

When a workflow must render admitted JSON into a terminal representation such
as SVG, that renderer follows the JSON-admission processor on the same private
workflow-local output edge. DAR passes bounded bytes between the fixed,
package-declared processors; it does not parse the intermediate JSON or expose
it as a terminal result. Only the final processor output is shaped against the
declared terminal output contract. The existing boolean terminal validator is
not a processor and cannot stand in for this edge.

### Private terminal processor contract

A terminal processor is a fixed package asset with declared byte and time
limits. It receives one private byte sequence on standard input and returns a
bounded JSON envelope on standard output:

```json
{
  "status": "accepted",
  "output_base64": "...",
  "repair_report": {
    "category": "none"
  }
}
```

`status` is exactly `accepted`; `output_base64` decodes to the next private
byte sequence. A JSON-admission processor's decoded output must be one strict
JSON object. A later renderer may consume those bytes and emit the final
terminal representation. The repair report is bounded, contains no completion
text, and names only the declared deterministic repair category. DAR retains
the original and admitted bytes in an authenticated, local-user diagnostic
record; public results and traces receive only their digests and the repair
category. No processor is discovered or selected at invocation time.

### Contract identifiers

`transformers-peft-single-image-v1` remains the preparation loader profile and
`transformers-peft-v1` remains the built-in runner catalog ID.
`transformers-generate-v1` is the converter-compatible runner execution
contract. A converter manifest shall match only the latter; these identifiers
are not aliases and have no fallback matching.

### Converter contract

A converter is a Python package asset with the manifest-declared entry point.
That entry point implements this standard contract:

```python
class InputConverterPlugin(Protocol):
    converter_contract_version: str
    compatible_runner_contract_id: str

    def pack(
        self,
        *,
        prompt: str,
        payload: SealedPayload,
        context: RestrictedRunnerInputContext,
    ) -> PackedModelInput: ...
```

`SealedPayload` supplies the bounded bytes for this invocation only. It does
not expose a source path, filename, URL, or caller metadata.
`RestrictedRunnerInputContext` exposes only the processor/model-input
facilities defined by the selected execution contract; it exposes neither
arbitrary model files nor model-selection controls. A converter may decode,
identify, transform, normalize, tokenize, or pack its bytes in any way that its
compatible runner can consume.

The first execution contract is `transformers-generate-v1`. Its runner loads
the reviewed base model and PEFT adapter, provides the reviewed processor in the
restricted context, receives an opaque mapping suitable for
`model.generate(**inputs)`, and performs bounded generation and output decode.
A JPEG/PNG Qwen converter is one implementation; a TIFF Qwen converter is a
different implementation. Neither changes DAR's core interface.

### Durable package identity

At registration, DAR shall validate and seal a converter manifest containing at
least:

```text
converter_id
converter_contract_version
compatible_runner_contract_id
entrypoint
asset_digest
declared_resource_limits
```

The converter asset digest, selected runner contract, model recipe digest, and
workflow package digest form the immutable binding for that registered workflow
instance. A generated converter becomes durable only through this binding. It
is not a host-wide installed plugin and cannot be reused by a different
workflow without a separate host registration decision.

## Functional Requirements

### FR-1: Exact selection and compatibility

DAR shall select a converter only from the registered workflow package and only
when its declared runner-contract ID exactly matches the selected runner. A
payload, prompt, generated text, filename, extension, or guessed format shall
not influence selection. Missing, duplicate, malformed, stale, or incompatible
converter assets fail before a model worker starts.

### FR-2: Opaque bytes at the DAR boundary

DAR shall treat the incoming payload as opaque bounded bytes. It may enforce
generic byte-count and lifecycle limits but shall not parse, sniff, decode, or
route based on file format. Format recognition and validation belong to the
converter. A converter's successful decode is its evidence that the bytes are
usable for its selected model contract.

### FR-3: Sealed Python-package execution

DAR shall load only the exact package-local Python entry point named by the
registered manifest, after digest and runner-contract verification. It shall
invoke that entry point through the standard converter interface with the
sealed payload, prompt, and restricted runner context. The converter cannot
select a different package, interpreter, model, runner, or invocation-time
callable.

This feature does not claim OS isolation from malicious converter code. Full
isolation is deferred to
[`../local-tool-sandbox-hardening/spec.md`](../local-tool-sandbox-hardening/spec.md)
and must not be represented as a current converter admission requirement.

### FR-4: Private packed-input handoff

The converter may return only a value accepted by its compatible runner. DAR
shall pass that value directly to the compatible standard runner and shall not
persist, trace, expose, reuse, or serialize it. The runner shall reject a
packed value that violates its contract without falling back to a different
converter, model, or remote execution path.

### FR-5: Host-owned limits and cleanup

DAR shall issue authoritative input-size, output-size, generation, and
cancellation limits. A converter cannot increase them. On success, failure,
timeout, cancellation, or runner rejection, the host shall clear the sealed
payload and dispose of packed state before returning a result.

### FR-6: Redacted lifecycle and failures

DAR shall trace only converter identity, declared contract version, selected
runner contract, bounded lifecycle state, and classified outcome. It shall not
trace raw payload bytes, decoded media, tensor data, prompt content beyond
existing policy, host paths, source code, environment values, or private
exception text.

Stable outward outcomes shall distinguish at least:

- converter unavailable or invalid;
- converter/runner contract mismatch;
- converter resource limit or timeout;
- converter input rejected;
- packed input rejected by the runner; and
- converter package load or execution failed.

### FR-7: Strict JSON constraint and admission

When a workflow declares exactly `response_format: {type: json_object}`, DAR
shall route that existing response-format request only to an adapter that
advertises `json_mode: true`. An adapter without that capability shall fail
before model loading, payload binding, or generation. A capable adapter shall
return strict JSON or fail the run; it shall not downgrade the request to prompt
guidance. JSON Schema support, domain-schema interpretation, and semantic
validation are outside this requirement.

### FR-8: Workflow-owned bounded repair

Any repair is a workflow-declared terminal output postprocessor with an exact
package asset and bounded input/output/time limits. It may make only
deterministic syntax repairs specified by its registered policy. It shall
strictly parse the result and reject truncation, ambiguous text, or any repair
requiring invented structure. Raw and repaired text remain private diagnostic
artifacts; DAR traces and public results contain only classified outcome,
bounded repair category, and digests.

### FR-7: Authoring and packaging boundary

An authoring system may emit a converter asset only in the fixed package form
validated by DAR. It cannot submit a live callable, install a dependency,
select an arbitrary interpreter, or grant itself additional capabilities. The
authoring system must declare the converter's compatible runner contract and
resource needs; DAR supplies the fixed standard runner context.

If no converter satisfies the required runner contract, the workflow authoring
result must identify that missing implementation rather than registering a
partial workflow. A future `agent-converter-designer` guidance asset may create
contract-conforming converter packages, but it must not bypass package
validation.

## Acceptance Criteria

- Fake-only contract tests prove DAR loads only the manifest-bound Python
  package entry point and gives it prompt, sealed bytes, and the restricted
  runner context.
- Fake-only tests prove an opaque packed value reaches only its exact compatible
  runner and is never persisted or returned through a DAR API, trace, or
  workflow artifact.
- Fake-only tests prove invalid manifests, digest mismatch, duplicate IDs,
  runner mismatch, malformed packed input, package-load failure, timeout, and
  cancellation produce stable redacted outcomes and clear package state.
- A real, manually authorized acceptance packages the Qwen floorplan converter,
  invokes the workflow through prompt plus sealed bytes, and returns a bounded
  normalized result without exposing conversion or model implementation details
  to the workflow user.

## Relationship to Existing Model Execution Plugins

`model-execution-plugin-interface` remains the extension point for a
client-installed model loader, generator, or output decoder that DAR cannot
express. This specification is narrower and workflow-scoped: it supplies only
the sealed-payload-to-packed-input step for a compatible standard runner.

When a model needs both a custom execution plugin and a workflow converter, the
converter must target that execution plugin's declared runner contract. The two
assets remain separately identified; neither may silently broaden the other's
contract.

## Deferred Decisions

- Define OS-level isolation for malicious local-tool or converter-package code
  in `local-tool-sandbox-hardening`; Docker and other full-isolation backends
  are future work and do not gate this package contract.
- Specify dependency packaging for converter packages when a second concrete
  package proves the existing standard runtime insufficient.
- Define promotion policy for an instance-sealed converter that a host wishes
  to review and make reusable.
- Decide whether a converter may receive an advisory caller-declared content
  label. Such a label must never be required for DAR routing or treated as a
  proof of the payload's actual format.
