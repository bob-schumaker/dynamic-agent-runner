# Workflow Locked Inference Callback Specification

## Metadata

- Feature slug: `workflow-locked-inference-callback`
- Status: proposed from external embedding-workflow feedback
- Owner: dynamic-agent-runner package, capability, material, and sandbox boundaries
- Plan: `plan.md`
- Tasks: `tasks.md`
- Related specifications:
  - `specs/workflow-model-materials/spec.md`
  - `specs/workflow-capability-requirements/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/workflow-embedding-index-artifacts/spec.md`

## Objective

Allow an approved sealed workflow-local asset to request bounded structured
inference from one separately locked DAR model per declared role without
learning a provider, endpoint, model path, device policy, credential, or
model-selection control.

## Scope

The package declares an `inference_roles` v1 descriptor mapping and one exact
package-level `model.generate.v1` capability requirement. Roles are sorted,
unique identifiers; each binds one unique material-set role, two sealed schema
assets, one sealed instruction asset, finite limits, and one or more explicitly
authorized sealed assets. Roles may share the single generation requirement;
they cannot name a provider. A receiving DAR installation resolves every role's
material and its receiver-local provider before package asset loading or sealed
input ingress.

The host passes an approved asset only a narrow callback:

```text
generate(role, canonical_request_bytes) -> canonical_response_bytes
```

The descriptor has exactly `format_version`, `roles`, and
`inference_roles_digest`; its canonical JSON bytes bind all role fields and
their referenced asset digests into package policy, registration, and export.
The parser rejects unknown/duplicate/unsorted fields and roles. A receiver that
does not support this descriptor version rejects it before asset import.

The initial v1 syntax is a non-empty lexically ordered `roles` array. A role
contains its identifier, distinct material-set role, literal
`model.generate.v1` capability ID, sealed instruction/request-schema/response-
schema assets (`path` plus SHA-256), sorted authorized callback-asset digests,
and positive `max_calls`, input/output-byte, timeout-millisecond, and
concurrency ceilings. `inference_roles_digest` is optional in source YAML but,
when present, must equal the SHA-256 of the canonical JSON information content;
registration and export always bind that digest.

Each role has canonical UTF-8 instruction bytes and separate canonical
structured-value-v1 request/result schema assets. Structured-value-v1 is a
restricted JSON dialect: object, array, string, boolean, null, required,
properties, items, enum, and explicit maximum depth/item/string-byte limits;
references, composition, numeric values, and unknown keywords are forbidden.
The host parses duplicate-key-free canonical JSON values and validates them
against the sealed schema before provider execution and before returning a
response. The host serializes the sealed instruction and canonical request
value as separate fixed model inputs; request data cannot override
instructions, tools, settings, or provider choice. This is a sealed data
projection, not a template language or prompt control plane.

The callback accepts only an asset-authorized role and a canonical bounded
structured value. It has no provider names, prompt fields, network options,
cache paths, or model execution settings. DAR validates both boundaries and
returns a redacted failure before a provider call on any mismatch.

`model.generate.v1` is deliberately domain-neutral. Classification,
extraction, normalization, summarization, and constrained suggestion are
potential consumers. DAR neither defines vocabulary membership, labels,
clusters, note fields, nor editing behavior.

## Non-Goals

This feature does not:

- define a tag, classification, or recommendation API;
- expose arbitrary prompt templates, provider-native tool calls, streaming,
  conversation history, or invocation-time model selection to a workflow asset;
- permit an asset to make a second unbound model call, chain arbitrary models,
  or inspect another material role;
- make raw callback input/output ordinary traces, errors, package receipts, or
  diagnostics; or
- bypass the approved isolation gate for untrusted package assets.

## Requirements

1. A descriptor declares each inference role with a material role, sealed
   instruction/request/result assets, exact shared capability requirement,
   authorized asset digests, and finite limits. Every reference resolves
   exactly; no inference role can be substituted or used by an unauthorized
   asset.
2. DAR derives one nonserializable private inference binding per role from the
   material-set/role/lock digest, runner/profile, exact capability contract,
   instruction/schema digests, and effective limits. It retains the selected
   provider executable handle privately; no package-visible receipt or
   telemetry exposes that handle or its settings.
3. Admission resolves every role before package-local asset import, material
   download, sealed input ingress, embedding execution, or result allocation.
   Revalidation immediately precedes every callback invocation and never falls
   back to another provider.
4. The internal provider seam is
   `generate(binding, instruction_bytes, request_bytes) -> response_bytes`;
   package assets see only the narrow callback. Effective per-role limits are
   the minimum of declared and host ceilings: calls, aggregate/per-call input
   and output bytes, timeout milliseconds, and concurrency. DAR atomically
   reserves a call budget before provider entry, does not retry, cancels on the
   deadline, discards late responses, and revokes the callback on asset exit.
   Provider output enters a bounded host-owned reader before parsing. Ordinary
   telemetry retains only binding digests, counts, and stable classifications.
5. A callback-enabled asset has a versioned ABI declaring its asset digest,
   authorized roles, sealed input artifacts, and ordered output slots (name,
   media type, schema digest, byte ceiling). It writes only declared outputs to
   the existing in-memory result collector. All slots seal atomically; a failed
   call, validation error, timeout, or absent/extra/repeated slot returns no
   result artifact or raw request/response in a host receipt.
6. A workflow-local asset can receive this callback only through an approved
   sealed-asset runtime profile. The experimental personal-use profile requires
   explicit authorization of the exact package and asset digests. General
   release and foreign-package execution remain gated on
   `local-tool-sandbox-hardening`.

## Acceptance Criteria

- Fake-only tests prove malformed inference-role descriptors, missing or
  mismatched instruction/schema assets, unknown/unauthorized role, limit,
  provider, material, and canonical-value failures perform zero package import,
  model load, provider call, and result allocation/write.
- Fake providers prove exact ordering, role isolation, response validation,
  revalidation, no fallback, atomic quota reservation, cancellation, and
  late-response disposal.
- An approved fixture package proves one bounded callback result can flow only
  through declared atomically sealed result slots with no raw request/response
  in ordinary traces, exceptions, reprs, or receipts.
