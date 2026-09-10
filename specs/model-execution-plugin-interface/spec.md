# Model Execution Plugin Interface Specification

## Metadata

- Feature slug: `model-execution-plugin-interface`
- Status: future work
- Owner: dynamic-agent-runner local-model and workflow-host boundaries
- Related specifications:
  - `specs/local-model-preparation/spec.md`
  - `specs/workflow-model-materials/spec.md`
  - `specs/local-model-runner-interface/spec.md`
  - `specs/model-adapter-coverage/spec.md`
  - `specs/workflow-input-converter-plugin/spec.md`

## Objective

Allow DAR to manage the preparation and execution lifecycle of local models
that do not fit a built-in compatibility profile, without accepting arbitrary
model code from a workflow, prompt, or remote model repository.

DAR continues to own artifact integrity, storage, execution lifecycle, resource
limits, cancellation, sealed ingress, tracing, approval, and normalized model
results. A client supplies a reviewed, versioned model-execution plugin only
for the model-specific loading or request/response behavior DAR cannot express
declaratively.

## Problem Statement

Some models require custom Python, vendor-specific loading, nonstandard image
or video packing, custom prompt/token construction, or bespoke output decoding.
A generic runner cannot safely guess those behaviors. Conversely, making every
such model a fully client-owned runner duplicates DAR's security and lifecycle
controls and forces clients to reimplement preparation, resource management,
and sealed-artifact handling.

## Scope

This feature defines:

1. declarative built-in compatibility profiles for standard model families;
2. a narrow receiver-installed provider contract for nonstandard execution
   behavior;
3. exact capability/material-lock/profile compatibility validation;
4. a verified installation and isolation model for plugin code; and
5. DAR-owned lifecycle, resource, ingress, tracing, and result boundaries.

## Non-Goals

This feature does not:

- permit `trust_remote_code=True` for arbitrary Hub content;
- define workflow-scoped generated input conversion; that narrower exception is
  owned by `specs/workflow-input-converter-plugin/spec.md` and requires its
  isolated-worker boundary;
- create a general-purpose Python sandbox or let a plugin inspect arbitrary
  host files, environment variables, credentials, or networks;
- standardize every inference framework or model architecture; or
- move workflow domain semantics such as floorplan/SVG validation into DAR.

## Architecture

### Declarative profiles first

DAR shall prefer built-in, declarative compatibility profiles such as
`transformers-peft-v1`. A material declaration selects one only when its loader,
media,
prompting, generation, and output behavior are within that profile's explicitly
documented limits. Unsupported behavior fails closed instead of invoking a
similarly named profile.

### Receiver-installed provider for exceptions

A receiver-installed provider is an installed package or executable registered
by the host, not content fetched or selected by a workflow material declaration.
Its registration records:

```text
plugin_id
plugin_version
plugin_distribution_digest
supported_execution_profiles
```

These fields are DAR-private provider identity and audit state. They establish
which public model-execution capability contracts the provider may implement;
they are not workflow package requirements or package-identity inputs.

A sealed workflow model-material declaration names one supported execution
profile and carries an immutable artifact closure. The package requires the
matching public model-execution capability; DAR selects a reviewed registered
provider for it. Plugin identity is receiver-private audit state, not an exact
package binding.

### Plugin contract

The exact language ABI is an implementation decision, but the conceptual
contract is:

```python
class ModelExecutionPlugin(Protocol):
    execution_profile_id: str

    def load(self, prepared: VerifiedPreparedArtifacts) -> LoadedModel: ...
    def encode(self, request: SealedModelRequest) -> EncodedRequest: ...
    def generate(
        self, model: LoadedModel, request: EncodedRequest, limits: GenerationLimits
    ) -> EncodedResult: ...
    def decode(self, result: EncodedResult) -> ModelResponse: ...
```

`VerifiedPreparedArtifacts` exposes only the exact read-only artifact members
declared by the sealed material lock. `SealedModelRequest` exposes bounded approved
text and media bytes/types, not arbitrary filesystem paths or URLs.
`GenerationLimits` is host-issued and authoritative. A plugin returns only a
bounded normalized result or a package-owned classified error.

The interface must support model-specific preprocessing, multimodal packing,
and decoding without giving the plugin authority over DAR registration,
preparation, persistence, user approval, tracing, or output-contract
validation.

## Security and Isolation Requirements

### FR-1: Verified plugin provenance

DAR shall load a plugin only when the host has explicitly registered its
identity, version, distribution digest, and declared execution profiles. A
material declaration cannot introduce a plugin identifier, package location, or
dependency at invocation time.

### FR-2: Least-privilege execution boundary

The plugin receives only verified read-only model artifacts, sealed request
content, and host-issued limits. It receives no ambient credentials, arbitrary
paths, caller-controlled environment values, or network authority. The
implementation shall define a process/isolation mechanism appropriate to each
supported platform before declaring a plugin profile production-ready.

### FR-3: Host-owned lifecycle and resources

DAR owns model residency, cleanup, concurrency, GPU/CPU/memory limits,
cancellation, timeout policy, trace emission, and error shaping. A plugin may
request declared resources but cannot exceed host policy or manage another
plugin's model instance.

### FR-4: Exact compatibility and fail-closed behavior

DAR validates the plugin, execution profile, material-lock identity, prepared artifact
closure, declared media contract, and model profile before loading. Missing,
duplicate, stale, incompatible, or disabled bindings fail before generation
and without fallback to remote code or a different plugin.

### FR-5: Auditable extension behavior

DAR traces plugin selection, load, generation lifecycle, resource decisions,
and classified failures using redacted metadata. Traces must not contain raw
sealed media, artifact paths, credentials, prompts beyond existing trace policy,
or plugin-private exception text.

## Acceptance Criteria

- A standard material declaration remains on a declarative DAR-owned runner and
  does not load
  a plugin.
- A nonstandard material declaration resolves only an explicitly registered
  plugin with an
  exact compatible profile and verified prepared artifact closure.
- Fake-only tests prove plugins cannot receive arbitrary paths, network access,
  or raw credentials through the DAR contract.
- A plugin requiring custom code cannot be activated by a Hub revision or
  workflow artifact alone.
- Resource exhaustion, timeout, cancellation, and plugin exceptions produce
  bounded package-owned failures and cleanup the model/sealed input state.

## Open Design Decisions

- Choose the first supported plugin packaging and isolation mechanism:
  subprocess protocol, platform sandbox, or in-process trusted extension.
- Define the portable artifact-mount abstraction without leaking host paths.
- Coordinate declared execution contracts with the opaque-byte workflow input
  converter boundary without defining a DAR media or tensor registry.
- Decide the compatibility and deprecation policy for registered plugins.
