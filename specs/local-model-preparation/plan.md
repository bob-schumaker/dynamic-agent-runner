# Local Model Preparation Implementation Plan

## Status

Historical implementation baseline. This plan's completed host-catalog slices
remain validation evidence for preparation mechanics. The current ownership
contract is [`../workflow-model-materials/spec.md`](../workflow-model-materials/spec.md),
which requires a new plan before implementation changes. The executable
checklist is [`tasks.md`](tasks.md).

## Goal

This historical baseline let a saved workflow name a logical local model once.
The successor contract instead seals an exact material declaration into the
workflow package; DAR retains the preparation mechanics described here without
exposing a path, cache layout, or generated handoff identifier to the user.

## Current-State Anchors

| Concern | Current owner | Planned change |
| --- | --- | --- |
| One-file Hub resolution and SHA validation | `local_models.py` | Reuse its file download and error boundary for individual recipe artifacts; do not turn it into a general model registry. |
| Shared Hub calls | `hugging_face_support.py` | Reuse the lazy, package-owned download seam with injected fakes in tests. |
| Direct llama.cpp construction | `LlamaCppLocalModelAdapter` and `LlamaCppLocalModelConfig` | Build the existing config only from a verified prepared artifact set. |
| Floorplan vision binding | `workflow_host/floorplan_vision_model.py` | Replace its placeholder base/projector configuration with host-private prepared paths, including the LoRA adapter setting. |
| Profile/host composition | `workflow_host/profiles.py` and `workflow_host/host.py` | Resolve a prepared set for the selected exact profile before constructing the adapter. |
| Saved-workflow invocation | `dar_package_cli.py` and `workflow_host/cli.py` | Add an explicit preparation operation and make invocation resolve ready sets without performing an implicit network download. |

## Delivery Rules

- Every slice starts with focused fake-only RED tests and records the expected
  failure before implementation.
- Historical only: recipe data was host-owned and a workflow descriptor
  retained only its logical model requirement, adapter, and capabilities.
- The successor material lock is package-bound. A host policy may authorize
  materialization during invocation; it still controls every network download.
- Preparation receives a logical requirement; no public command accepts a base,
  projector, LoRA, or converter path.
- Existing single-file local-model resolution and callers remain unchanged.

## S1 — Recipe and prepared-set contracts

1. Write RED tests for exact requirement-and-adapter lookup, unknown recipe
   rejection, no similar-name fallback, immutable catalog values, and path-free
   public readiness/failure results.
2. Add immutable, package-owned recipe value objects for a logical requirement,
   exact adapter, pinned source artifact, optional deterministic transformation,
   and prepared artifact set. Keep physical paths private to the host-facing
   result.
3. Add the fixed floorplan recipe from the spec, including all source revisions,
   filenames, digests, converter revision/environment identity, output digest,
   base/projector/LoRA roles, and F16 output requirement.

Exit: DAR can identify one complete, pinned floorplan recipe without a Hub call,
model load, conversion, or workflow-package change.

## S2 — Deterministic preparation and cache validation

1. Write RED tests for complete cache hit, partial cache hit, missing source,
   download authorization denial, integrity mismatch, and no inspection of
   unrelated directories. Fakes must prove which exact per-file downloader and
   converter inputs are called.
2. Add a host-owned preparation service that inspects only the DAR preparation
   cache, the existing default Hugging Face cache, and an explicit permitted
   cache root. It revalidates source and generated artifacts before reporting a
   set ready.
3. Implement per-file download through the existing Hugging Face support seam.
   Do not use snapshot downloads for the fixed recipe. Stage generated output
   privately and promote it only after format and digest verification.
4. Introduce an injected, reviewed conversion collaborator for the fixed
   llama.cpp converter environment. It receives the declared LoRA and base
   metadata only; failed or interrupted conversion leaves no ready output.

Exit: `prepare` can produce or reuse a verified artifact set under the logical
model name, with deterministic fake-only coverage and no ambient converter
environment.

## S3 — Verified llama.cpp vision composition

1. Add RED tests showing that the floorplan adapter receives only the prepared
   base GGUF, matching projector, and converted LoRA; none can be replaced by a
   prompt, workflow descriptor, or arbitrary caller path.
2. Change the floorplan configuration/factory to accept the host-private
   prepared set rather than placeholders. Preserve its sealed-image delivery,
   exact adapter identity, and rejection before a model call when a required
   artifact is unavailable.
3. Thread prepared-set resolution through the profile and host adapter factory.
   A profile mismatch, missing recipe, stale set, or invalid set fails closed
   before adapter construction.
4. Preserve existing text-only and Fastmail llama.cpp configuration behavior
   with focused regression tests.

Exit: a ready floorplan set composes the existing llama.cpp adapter correctly,
while all other local-model paths retain their current behavior.

## S4 — Host and package invocation surface

1. Add RED CLI and host tests for unknown recipe, unauthorized preparation,
   cache-only success, verified preparation success, and failure redaction.
   Assert that neither arguments nor responses accept or reveal artifact paths
   or generated identifiers.
2. Add a host operation and narrow package command equivalent to
   `prepare <logical-model-requirement>`. It returns only a stable readiness or
   redacted failure result under that same logical name.
3. Make saved-workflow invocation resolve the workflow's declared requirement
   against ready prepared sets. It must return a concise ready-to-prepare or
   unavailable result when absent, and it must make no network call.
4. Update the Agent Engineering DAR guidance only to request the host-owned
   preparation operation when an authorized composition needs it. It must not
   generate paths, converter commands, or user-visible preparation handles.
   Regenerate and validate the plugin payload after that source guidance change.

Exit: the user can prepare a known logical model and invoke the saved workflow
without providing physical locations or a preparation receipt.

## S5 — End-to-end evidence and release gate

1. Run the focused fake-only suites from S1–S4, then the full repository test
   suite and configured formatting/lint gates.
2. Run one manually authorized acceptance test with the pinned floorplan recipe:
   prepare/reuse the artifacts, compose llama.cpp with the base/projector/LoRA,
   ingress one sealed image, execute the saved workflow, admit its structured
   JSON model output, and validate the resulting SVG terminal artifact.
   JSON-to-SVG rendering and SVG validation remain downstream workflow-local
   tooling. This is outside unit tests and records only redacted identities and
   verification outcomes.
3. Verify no user-facing output, trace, workflow descriptor, or plugin guidance
   contains an artifact path, cache root, converter command, or opaque handoff
   identifier.
4. Update `tasks.md`, validation evidence, and release/package artifacts only
   after every required check is green.

Exit: the floorplan workflow executes through the logical model requirement
alone, and all deterministic and manual evidence required by the spec exists.

## Deferred Decisions

- The exact public Python and CLI names remain implementation choices; package
  material admission is package-bound and has no model-named preparation CLI.
- Recipes beyond the fixed floorplan model require separately reviewed additions;
  Hub search is not a fallback catalog.
- Converter sandboxing and arbitrary-model recipe authoring are outside this
  feature. The existing local-tool sandbox-hardening work owns the former.
