# Workflow Input Converter Plugin Specification

## Metadata

- Feature slug: `workflow-input-converter-plugin`
- Status: future work
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
that registered workflow instance and runs as untrusted code. DAR validates its
identity and execution contract, confines it to an isolated model worker, and
never needs format-specific knowledge such as JPEG, TIFF, GIF, PCAP, or
protobuf.

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
4. isolation, lifecycle, resource, and failure requirements for generated
   converter code; and
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
- grant converter code network access, caller workspace access, credentials,
  ambient environment access, or host callbacks;
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

Inside the isolated model worker, the execution shape is:

```text
sealed payload bytes + prompt
  -> workflow-sealed InputConverterPlugin.pack(...)
  -> opaque PackedModelInput
  -> compatible StandardModelRunner.generate(...)
  -> normalized text result
```

`PackedModelInput` is private to the worker and to the declared runner
execution contract. It can be a mapping of framework tensors for
`transformers-generate-v1`, but DAR neither inspects nor serializes it. There is
no universal tensor schema.

The converter is a private graph node. The package can declare it for
validation and trace identity, but a workflow user cannot invoke it directly
and no graph edge exposes decoded input or packed state outside the worker.

### Converter contract

The implementation language and ABI are deliberately open. Every converter
must be adapted to this conceptual contract:

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
not expose a source path, filename, URL, caller metadata, or capability to
retain the input. `RestrictedRunnerInputContext` exposes only the
processor/model-input facilities defined by the selected execution contract;
it exposes neither arbitrary model files nor a host filesystem. A converter may
decode, identify, transform, normalize, tokenize, or pack its bytes in any way
that its compatible runner can consume.

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

### FR-3: Isolated generated-code execution

Converter and compatible runner shall execute in an isolated worker selected by
the host. The worker receives only read-only verified model material, the
sealed payload, the prompt, the converter asset, and host-issued limits. It
shall have no network, inherited credentials, ambient writable directory,
caller workspace visibility, arbitrary process execution, or authority to load
undeclared code.

The platform isolation backend must meet the enforcement requirements of
`specs/local-tool-sandbox-hardening/spec.md`. An opaque Python interface or a
same-process callback is not isolation. Until that backend exists, this feature
may have trusted development fixtures only; it is not production-ready for
generated converter assets.

### FR-4: Private packed-input handoff

The converter may return only a value accepted by its compatible runner. DAR
shall pass that value directly inside the same isolated worker and shall not
persist, trace, expose, reuse, or serialize it. The runner shall reject a
packed value that violates its contract without falling back to a different
converter, model, or remote execution path.

### FR-5: Host-owned limits and cleanup

DAR shall issue authoritative timeout, memory, CPU/GPU, input-size, output-size,
and cancellation limits. A converter cannot increase them. On success, failure,
timeout, cancellation, worker crash, or runner rejection, the host shall clear
the sealed payload and terminate/dispose of worker-local packed state before
returning a result.

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
- isolated worker unavailable or failed.

### FR-7: Authoring and packaging boundary

An authoring system may emit a converter asset only in the fixed package form
validated by DAR. It cannot submit a live callable, install a dependency,
select an arbitrary interpreter, or grant itself additional capabilities. The
authoring system must declare the converter's compatible runner contract and
resource needs; DAR supplies the actual isolation policy.

If no converter satisfies the required runner contract, the workflow authoring
result must identify that missing implementation rather than registering a
partial workflow. A future `agent-converter-designer` guidance asset may create
contract-conforming converter packages, but it must not bypass package
validation or isolation.

## Acceptance Criteria

- Fake-only contract tests prove a registered converter receives prompt and
  sealed bytes but no paths, ambient environment, network, credentials, or
  arbitrary callback capability.
- Fake-only tests prove an opaque packed value reaches only its exact compatible
  runner and is never persisted or returned through a DAR API, trace, or
  workflow artifact.
- Fake-only tests prove invalid manifests, digest mismatch, duplicate IDs,
  runner mismatch, malformed packed input, worker failure, timeout,
  cancellation, and resource exhaustion produce stable redacted outcomes and
  clear worker state.
- A capability-enforcement acceptance proves generated converter code cannot
  read an undeclared host file, write outside its ephemeral boundary, access the
  network, inherit a credential, or spawn an undeclared process.
- A real, manually authorized acceptance packages a converter for a model input
  that DAR does not understand, invokes the workflow through prompt plus sealed
  bytes, and returns a bounded normalized result without exposing conversion or
  model implementation details to the workflow user.

## Relationship to Existing Model Execution Plugins

`model-execution-plugin-interface` remains the extension point for a
client-installed model loader, generator, or output decoder that DAR cannot
express. This specification is narrower and workflow-scoped: it supplies only
the sealed-payload-to-packed-input step for a compatible standard runner.

When a model needs both a custom execution plugin and a workflow converter, the
converter must target that execution plugin's declared runner contract. The two
assets remain separately identified and isolated; neither may silently broaden
the other's capabilities.

## Deferred Decisions

- Select the first portable isolated-worker transport and define how the
  compatible runner and converter share in-memory packed data without a public
  tensor serialization format.
- Specify dependency packaging and allowlisted runtime libraries for converter
  assets without enabling dynamic installation or arbitrary imports.
- Define promotion policy for an instance-sealed converter that a host wishes
  to review and make reusable.
- Decide whether a converter may receive an advisory caller-declared content
  label. Such a label must never be required for DAR routing or treated as a
  proof of the payload's actual format.
