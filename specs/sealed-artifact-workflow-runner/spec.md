# Sealed Artifact Workflow Runner Specification

## Metadata

- Feature slug: `sealed-artifact-workflow-runner`
- Status: approved for implementation
- Owner: dynamic-agent-runner host package admission and execution boundaries
- Plan: `plan.md`
- Tasks: `tasks.md`

## Objective

Provide one domain-neutral receiver runtime for a durable workflow package that
transforms declared sealed input artifacts into declared sealed output artifacts
through approved workflow-local assets and host-owned bounded capabilities.

## Scope

The package declares a versioned artifact-runner descriptor: exact asset digest,
ordered required and optional input roles, ordered output slots with media type,
schema digest, and byte ceiling, exact capability requirements, callback
bindings, and a runtime-profile identity. Its canonical digest binds package
registration and ZIP export. Invocation accepts only opaque prepared-artifact
handles; it never accepts a path, URL, model, provider, endpoint, executable,
or output destination.

### Canonical v1 descriptor

The package-root `sealed-artifact-runner.json` is duplicate-key-free canonical
UTF-8 JSON. Its exact keys are `format_version`, `asset`, `inputs`, `outputs`,
`schemas`, `capability_requirements_digest`, `profile_digest`, `callbacks`,
`child_contract_digests`, `limits`, and `artifact_runner_digest`; unknown,
omitted, duplicate, or noncanonical fields fail before asset import.

`format_version` is the non-Boolean integer `1`. A digest is exactly 64 lowercase
hexadecimal characters. A package path is relative POSIX text with no empty,
`.` or `..` segment, and resolves to a regular ZIP entry. A role and callback
name matches `[a-z][a-z0-9_]{0,63}`. Inputs and outputs are sorted by `role`,
schemas by `path`, callbacks by `name`, and child-contract digests by their
text; none contains duplicates. No number may be a Boolean, negative,
fractional, nonfinite, or greater than `9007199254740991`.
A media type is lowercase ASCII `type/subtype` without parameters, where each
component matches `[a-z0-9!#$&^_.+-]+`.

| Field | Exact v1 value |
| --- | --- |
| `asset` | An object exactly `{abi_version: 1, entrypoint: "run", path: package-path, sha256: digest}`; its path has a `.py` suffix. |
| `inputs` | Ordered `{max_bytes: positive-integer, media_type: string, required: boolean, role: role, schema_digest: digest-or-null}` records. |
| `outputs` | Nonempty ordered `{max_bytes: positive-integer, media_type: string, role: role, schema_digest: digest-or-null}` records; every slot is required. |
| `schemas` | Ordered `{dialect: "json-schema-draft-2020-12", path: package-path, sha256: digest}` records. A non-null `schema_digest` resolves to exactly one listed schema with the same digest; it is valid only for `application/json`. A null digest declares opaque bytes and has no schema validation. |
| `callbacks` | Ordered `{child_contract_digest: digest, max_calls: positive-integer, max_concurrency: positive-integer, max_request_bytes: positive-integer, max_response_bytes: positive-integer, max_total_request_bytes: positive-integer, max_total_response_bytes: positive-integer, name: callback-name, requirement: string, timeout_milliseconds: positive-integer}` records. `requirement` equals exactly one `capability_id` in the canonical capability-requirements record named by `capability_requirements_digest`; that record supplies its version and contract digest. |
| `child_contract_digests` | Ordered unique digests. Every callback child digest appears here; a consumer-specific contract may add a digest without adding a callback. |
| `limits` | `{max_concurrency, max_cpu_milliseconds, max_io_bytes, max_memory_bytes, max_runtime_milliseconds}`, each a positive integer. Effective limits are the minimum of the descriptor and host ceilings. |
| `capability_requirements_digest`, `profile_digest` | A digest each. The profile digest identifies one host-known profile; it is never a package-selected executable. |

Every listed schema file is strict UTF-8 JSON with duplicate keys rejected and
validates as JSON Schema Draft 2020-12 before it may resolve a `schema_digest`.
An invalid schema is an admission-step-2 rejection before identity resolution.

The canonical bytes are strict UTF-8 without a BOM, decoded with duplicate keys
rejected, then encoded as the recursively key-sorted JSON object with `,` and
`:` as its only separators, ASCII escaping enabled, arrays preserved in declared
order, and nonfinite numbers rejected. `artifact_runner_digest` is SHA-256 of
those bytes after omitting that field. The following self-excluding payload is a
normative canonicalization vector; its digest is
`2c3ed7f8dc3c1aefe51d97bfc699bb7de6c5c5239a6b7a0df025acbf2ebb13f4`:

```json
{"asset":{"abi_version":1,"entrypoint":"run","path":"assets/example.py","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"callbacks":[],"capability_requirements_digest":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","child_contract_digests":[],"format_version":1,"inputs":[],"limits":{"max_concurrency":1,"max_cpu_milliseconds":1,"max_io_bytes":1,"max_memory_bytes":1,"max_runtime_milliseconds":1},"outputs":[{"max_bytes":1,"media_type":"application/octet-stream","role":"result","schema_digest":null}],"profile_digest":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","schemas":[]}
```

The established `package-manifest.json` remains the sole ZIP manifest. It lists
the descriptor, asset, and every schema as regular-file `files` entries and adds
`sealed_artifact_runner_digest` equal to the descriptor digest. A publisher-
signed ZIP signs that canonical manifest through the established
`package-signature.json` trust-key path. A locally selected personal package
instead binds the staged content digest in a host registration record. ZIP
staging rejects duplicate entries, non-regular entries, and noncanonical paths
before this descriptor is considered.

Every child-contract digest resolves to exactly one canonical JSON regular-file
entry in that manifest. A callback's child contract has a common v1 envelope
with exactly `{body: object, callback_name: callback-name,
capability_requirement: capability-id, format_version: 1}`; duplicate or
unknown envelope fields fail. `callback_name` and `capability_requirement`
exactly equal the parent callback's `name` and `requirement`; only `body` is
parsed by the consumer that owns the detailed payload semantics. The callback requirement
must match exactly one `capability_id` in the descriptor named by
`capability_requirements_digest`. Unresolved, duplicate, ambiguous, or
mismatched child contracts fail in admission step 2 before identity resolution.

### Artifact handle lifecycle

The host first creates an owner-authorized invocation record, then issues opaque
input handles bound to receiver identity, workflow revision, invocation, role,
digest, media/schema metadata, byte count, expiry, and owner. Only the issuing
receiver may resolve them. Required inputs must be present; optional inputs are
omitted rather than represented by null. The state transitions are:

| Artifact or invocation | States and terminal behavior |
| --- | --- |
| Invocation | `opened` → `prepared` → atomically `running` → `completed`, or from any nonterminal state → `rejected` / `failed` / `cancelled` / `expired` / `revoked`. A terminal failure retains only a redacted classification. A second invocation attempt fails as a replay. |
| Input handle | `prepared` → atomically `reserved` → `consumed`, or from a nonterminal state → `revoked` / `expired`. A terminal invocation failure revokes every reserved input; none can be retried. Metadata is checked before byte access. |
| Output candidate | private only while `collecting`; it becomes `sealed` only when every declared slot validates. Any error, cancellation, timeout, or failed finalization destroys all candidate bytes. |
| Output handle | created only by the `sealed` transition, bound to the owner and normal artifact-service expiry/revocation policy; export or persistence remains a separate owner-authorized operation. |

Cancellation that wins before the atomic seal returns no output handle. Completion
that wins after seal returns the sealed handles, which remain subject to normal
expiry and export authorization. The host records the linearization result and
never exposes temporary bytes, partial handles, or raw artifact data.

Before copying caller bytes or issuing a prepared input handle, the preparation
service performs descriptor and manifest verification plus side-effect-free
capability, material, and provider identity resolution for that target revision.
It validates the selected role, declared media type, byte ceiling, SHA-256, and,
for a non-null JSON schema, strict UTF-8 JSON with duplicate keys rejected and
schema validation. It then seals immutable private bytes and records the
verified digest and metadata. It defers material loading and provider entry.
Invocation repeats identity checks, requires the recompiled private selected
provider IDs to equal the registration-bound IDs, revalidates that exact saved
selection without reselection, and validates the handle binding and state.
`read_input` rechecks the sealed bytes' digest before returning them. A failure
occurs before asset, callback, or provider entry.

### Asset execution ABI and admission

ABI v1 treats the verified `.py` asset bytes as one import-disabled module and
calls only `run(context) -> None`. Its namespace has only the profile's fixed
allowlisted runtime helpers and no `__import__`, package-relative import,
import hook, or manifest-discovered code path; an undeclared module request
fails before invocation. This packaging rule identifies all package-local code
that executes as the authorized asset bytes. It is not an OS-isolation claim for
the experimental profile. `context.read_input(role) -> bytes` permits at most
one read for each declared role after validation.
`context.invoke_callback(name, request: bytes) -> bytes` permits only a
declared callback; and
`context.callback_identity(name) -> {"asset_digest", "child_contract_digest",
"digest"}` permits an asset to read only the exact identity of one callback it
already declares. `digest` is the SHA-256 of canonical ASCII JSON
`{"asset_digest": asset_digest, "child_contract_digest": child_contract_digest}`.
It exposes no package path, descriptor bytes, provider, material, handle, or
execution setting. This closes the otherwise circular case where a sealed asset
must bind an output to an identity that includes its own digest; and
`context.write_output(role, media_type, content: bytes) -> None` permits exactly
the next unresolved output role in descriptor order. An out-of-order, repeated,
or extra write destroys the collector. The host validates the supplied media
type, byte ceiling, and, for a non-null schema digest, JSON Schema Draft 2020-12
before
writing to the existing byte collector. `run` must return only after writing
every output; an asset cannot enumerate context members or obtain a collector,
provider, path, handle record, or host capability object.

For every non-null JSON schema, input and output bytes are strict UTF-8 JSON
with duplicate keys rejected before schema validation; malformed JSON or a
duplicate key fails before callback/provider entry for an input and before
collector write for an output.

Callbacks use only their descriptor table: request and response are opaque bytes
to the generic runner, while the bound child contract defines their detailed
payload semantics. The runner enforces the declared call, aggregate/per-call
I/O, deadline, and concurrency limits, revalidates the exact provider
immediately before entry, never falls back, and revokes callbacks before asset
teardown. Late results are discarded. The asset limits have the same host-minimum
rule; cancellation revokes callbacks and destroys the collector.
`max_io_bytes` counts every input byte returned, callback request byte supplied,
callback response byte returned, and output byte supplied to `write_output`,
before semantic validation; an overage fails the invocation.

Admission order is fixed: (1) provenance and owner eligibility from a trusted
host registration record keyed by receiver and workflow revision, with no ZIP
or artifact byte access; (2) ZIP, manifest, descriptor, schema, and asset-digest
verification against that record; (3) exact receiver-owner-package-revision-
asset-profile authorization; (4) side-effect-free capability, material, and
provider identity resolution, including equality and revalidation of the
registration-bound selected provider IDs; (5) handle metadata validation; (6)
collector allocation; then (7) asset import and execution. Material
download/load and provider entry are deferred to an authorized callback after
step 5. Any
rejection before its boundary performs zero later action, including input byte
reads, asset import, material download/load, provider call, collector
allocation/write, output-handle creation, or egress.

An isolated profile must deny ambient filesystem, network, subprocess,
environment, credential, import-escape, and capability-object introspection.
The experimental personal-use profile instead makes no OS-isolation claim: it
requires revocable exact authorization of the receiver owner, staged package
revision digest, asset digest, and profile digest, and it may run only a
locally selected owner package. Foreign or untrusted assets remain gated on
`local-tool-sandbox-hardening`.

Receiver admission verifies provenance, descriptor bytes, capability and model
bindings, asset authorization, and input contract before asset import, model
materialization, provider invocation, input consumption, or result allocation.
The runner exposes an approved asset only sealed input bytes, narrow
host-owned capability callbacks, and an empty bounded result collector. It
atomically seals every declared output or returns no output artifact. Normal
receipts/traces retain only digests, byte counts, and stable classifications.

The initial personal-use profile requires exact receiver authorization of the
package and asset digests. Foreign/untrusted assets remain gated on
`local-tool-sandbox-hardening`.

## Non-Goals

This runner does not define document, embedding, vector, index, cluster, tag,
prompt, inference-output, storage, or filesystem semantics. It does not expose
arbitrary Python callbacks, subprocesses, network access, host paths, or model
selection to package assets.

## Requirements

1. Package descriptors and ZIP manifests bind the artifact ABI digest, exact
   assets, required capabilities, and declared outputs.
2. A receiver resolves and revalidates private capability providers before each
   callback without fallback or provider disclosure.
3. Asset execution is revocable and bounded; malformed, unauthorized, or
   incomplete work has no output-artifact publication or egress. Any collector
   and candidate bytes are private, disposable working state.
4. Output collectors accept exactly the declared ordered slots and seal them
   atomically. Caller persistence is a separate explicit operation.

Collector validation checks media type, schema, byte ceiling, and exactly one
write per output. Missing, extra, repeated, invalid, timed-out, cancelled, or
exceptional execution returns no output handle, result, or raw data receipt.

## Integration

`workflow-embedding-index-artifacts` defines an index-builder asset as one
consumer. `workflow-locked-inference-callback` defines a capability callback
available to such assets. `workflow-capability-requirements` owns exact
capability matching; `sandbox-workspace-runtime` owns the execution profile.
This spec owns the outer descriptor, invocation, and egress; consumer specs
bind their child descriptor digests into it and must not define parallel asset
invocation routes.
