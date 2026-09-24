# DAR Multimodal Model Runner Protocol Specification

## Metadata

- Feature slug: `multimodal-model-runner-protocol`
- Artifact type: new host-extension interface specification
- Status: proposed
- Owner: dynamic-agent-runner workflow-host boundary
- Related artifacts:
  - [`external-model-adapter-protocol`](../external-model-adapter-protocol/spec.md)
  - [`local-model-runner-interface`](../local-model-runner-interface/spec.md)
  - [`workflow-model-materials`](../workflow-model-materials/spec.md)
  - [`model-generation-resource-budgets`](../model-generation-resource-budgets/spec.md)

## Objective

Define a future DAR host-extension boundary for sealed multimodal model
execution, including Transformers/PEFT and other prepared image/text runners.
This protocol is not a widening of `DARExternalAdapterProtocol`; it is a
resource- and artifact-aware runner contract for workflows whose input or
output is not text-only.

## Why this is separate

Multimodal runners have sealed material closures, input converters, device and
memory policy, bounded worker lifecycle, and workflow-owned output validators.
Those responsibilities do not fit a simple external model descriptor and
single text response. Treating them as ordinary external adapters would leak
paths and provider details or make the generation protocol responsible for
workflow-domain artifacts.

## Proposed boundary

The exported host extension is named `DARMultimodalModelRunnerProtocol` with
wire ID `dar.multimodal-runner.v1`. It is installed and admitted by the
receiver, like other reviewed host extensions, and provides:

```python
class DARMultimodalModelRunnerProtocol(Protocol):
    runner_id: str
    protocol_id: Literal["dar.multimodal-runner.v1"]
    protocol_version: Literal["1.0"]

    def describe(self) -> MultimodalRunnerDescriptor: ...
    def health(self) -> MultimodalRunnerHealth: ...
    def run(
        self,
        request: SealedMultimodalRequest,
        *,
        context: DARGenerationRequestContext,
    ) -> MultimodalRunnerResult: ...
```

The request must contain opaque, receiver-created sealed artifact handles and
declared logical roles. It must not contain raw paths, credentials, arbitrary
material roots, or workflow-supplied native runtime objects.

## Descriptor and lifecycle

The descriptor binds runner ID, provider/runtime ID, material-lock digest,
execution ABI, input/output modality set, converter digest, output-contract
digest, resource limits, and contract digest. Admission is exact and fail
closed. A runner must expose bounded health without loading unadmitted
materials.

The host owns placement, staging, worker containment, generation budgets,
approval, tracing, cleanup, and receipt publication. The runner owns only the
provider call and translation between sealed logical inputs and normalized
results. The workflow owns prompts, JSON/SVG/image contracts, and domain
validators.

## Result contract

Results contain normalized text or opaque sealed artifact handles, aggregate
token/byte/coverage scalars, and a worker-reaped attestation. Raw images,
model paths, prompts, native response objects, process IDs, and credentials
must not cross the boundary or enter receipts.

## Initial migration target

The first implementation target is the existing prepared Transformers/PEFT
runner for the floorplan workflow. It must preserve its sealed material and
input-converter contracts while moving host composition behind this protocol.
Other multimodal or native runners require separate capability rows, not
implicit support.

## Non-goals

- No change to the text-only external adapter protocol.
- No generic provider SDK abstraction.
- No workflow-domain prompt, SVG, JSON, or image validation inside DAR's
  protocol core.
- No arbitrary plugin-supplied code execution without receiver admission.
- No automatic model conversion, download, or material discovery.
- No streaming or persistent session semantics in v1.

## Acceptance criteria

- Missing or mismatched material, converter, ABI, output-contract, or resource
  facts refuse before worker creation or sealed-input ingress.
- A valid request reaches exactly one admitted runner with opaque sealed inputs.
- Budget exhaustion, cancellation, and worker failure produce bounded,
  redacted terminal results and confirmed cleanup.
- A result from another package, revision, converter, or material closure is
  rejected as non-transferable.
- Deterministic fake-runner tests prove admission, lifecycle, accounting,
  response shaping, and worker reaping without a live model.
- The floorplan workflow remains the owner of domain validation and publication.
