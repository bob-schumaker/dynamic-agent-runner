# Sealed Artifact Workflow Runner Specification

## Metadata

- Feature slug: `sealed-artifact-workflow-runner`
- Status: proposed
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
schema digest, and byte ceiling, and exact capability requirements. Its
canonical digest binds package registration and ZIP export. Invocation accepts
only opaque prepared-artifact handles; it never accepts a path, URL, model,
provider, endpoint, executable, or output destination.

### Canonical v1 descriptor

The package-root `sealed-artifact-runner.json` is duplicate-key-free canonical
UTF-8 JSON. Its exact keys are `format_version`, `asset`, `inputs`, `outputs`,
`capability_requirements_digest`, `limits`, and `artifact_runner_digest`.
`format_version` is integer `1`; all other scalar values are strings except
positive integer limits. `asset` is `{path,sha256,abi_version}`; paths are
package-relative and `abi_version` is `1`. Input and output role names match
`[a-z][a-z0-9_]{0,63}`, are lexically ordered and unique. Inputs declare
`role`, `required`, media type, schema digest, and byte ceiling. Outputs declare
`role`, media type, schema digest, and byte ceiling; all are required. The
digest excludes its own field and is SHA-256 of recursively sorted compact JSON.
The workflow descriptor, registration, and signed ZIP manifest bind that digest
and the exact asset digest; unknown, omitted, duplicate, or noncanonical fields
fail before asset import.

### Artifact handle lifecycle

The host issues opaque handles bound to receiver identity, workflow revision,
invocation, role, digest, media/schema metadata, byte count, expiry, and owner.
Only the issuing receiver may resolve them. Required inputs must be present;
optional inputs are omitted rather than represented by null. Handles are
single-use for invocation, revoked on expiry/cancellation, and rejected before
byte access on owner/revision/role/schema/digest mismatch. Output handles are
created only after atomic sealing; a caller may export or persist one only by a
separate owner-authorized operation.

### Asset execution ABI and admission

The receiver invokes the exact asset through one approved runtime profile with
read-only role-addressed input bytes, a fixed capability-callback namespace,
and the existing bounded result collector. Callbacks have independently
declared schema, call, aggregate/per-call I/O, deadline, and concurrency limits.
They are revalidated immediately before entry, never fall back, and are revoked
before asset teardown; late results are discarded. The asset has finite runtime,
CPU/memory/I/O, and concurrency ceilings; cancellation revokes callbacks and
destroys the collector.

Admission order is fixed: provenance/owner authorization; manifest/descriptor/
asset-digest verification; requirements/material/provider binding; handle
metadata validation; collector allocation; then asset import and execution.
Any rejection before its boundary performs zero later action, including input
byte reads, asset import, material download/load, provider call, collector
allocation/write, output-handle creation, or egress.

The profile denies ambient filesystem, network, subprocess, environment,
credential, import-escape, and capability-object introspection. Exact personal
authorization binds receiver owner, package revision digest, asset digest, and
profile and is revocable before every invocation; untrusted assets remain gated.

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
   incomplete work has no result allocation or egress.
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
