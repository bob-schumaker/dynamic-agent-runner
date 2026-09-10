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
inference from one separately locked DAR model without learning a provider,
endpoint, model path, device policy, credential, or model-selection control.

## Scope

The package declares one or more immutable inference roles, each bound to a
named entry in a sealed model-material set and one exact `model.generate.v1`
capability requirement. A receiving DAR installation resolves the material and
receiver-local provider before package asset loading or sealed input ingress.

The host passes an approved asset only a narrow callback:

```text
generate(role, canonical_request_bytes) -> canonical_response_bytes
```

The role, input schema digest, output schema digest, maximum call count, and
input/output byte limits are immutable descriptor data. The callback accepts
only a declared role and canonical bounded structured values; it does not
accept provider names, prompts as an alternate control plane, tools, network
options, cache paths, or model execution settings. DAR validates both callback
boundaries and returns a redacted failure before a provider call on any
mismatch.

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

1. A descriptor declares each inference role with a material role, exact
   capability requirement, canonical request/result schema digests, and finite
   resource limits. A role occurs once and all declared material/capability
   references resolve exactly.
2. DAR derives a private inference binding from the selected material lock,
   runner/profile, exact capability contract, and declared callback limits. It
   contains no provider identity or execution setting.
3. Admission resolves every role before package-local asset import, material
   download, sealed input ingress, embedding execution, or result allocation.
   Revalidation immediately precedes every callback invocation and never falls
   back to another provider.
4. A provider receives only canonical request bytes and returns canonical result
   bytes. DAR enforces role, schema, call, byte, timeout, and host-ceiling
   limits on both sides and retains only binding digests, counts, and stable
   classifications in ordinary telemetry.
5. A workflow-local asset can receive this callback only through an approved
   sealed-asset runtime profile. The experimental personal-use profile requires
   explicit authorization of the exact package and asset digests. General
   release and foreign-package execution remain gated on
   `local-tool-sandbox-hardening`.

## Acceptance Criteria

- Fake-only tests prove unknown role, schema, limit, provider, material, and
  canonical-value failures perform zero package import, model load, provider
  call, and result write.
- Fake providers prove exact ordering, role isolation, response validation,
  revalidation, and no-fallback behavior.
- An approved fixture package proves one bounded callback result can flow only
  through a declared opaque result artifact with no raw request/response in
  ordinary traces or receipts.
