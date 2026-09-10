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

## Integration

`workflow-embedding-index-artifacts` defines an index-builder asset as one
consumer. `workflow-locked-inference-callback` defines a capability callback
available to such assets. `workflow-capability-requirements` owns exact
capability matching; `sandbox-workspace-runtime` owns the execution profile.
