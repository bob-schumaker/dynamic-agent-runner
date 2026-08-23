# DAR Authoring Plugin Implementation Tasks

## Status

This task breakdown implements the release gates in `spec.md`. Complete each
task test-first; a later gate cannot be implemented or advertised as live before
its predecessors pass.

## G0: Package and Server Spike

- [ ] RED: plugin-manifest discovery and isolated-installation tests.
- [ ] GREEN: create the `dar-authoring` plugin bundle and local stdio MCP server
      entrypoint without undocumented path interpolation.
- [ ] RED/GREEN: start/stop lifecycle test that proves the server exposes no
      execution tool before G1–G3 are configured.

## G1: Catalog, Profile, and Capability Boundary

- [ ] RED: versioned `run_dar_workflow` request/response schema tests for
      closed-set workflow, operation, and profile identifiers.
- [ ] GREEN: immutable package/operation catalog with artifact, catalog, and
      profile digests; reject arbitrary package paths, endpoints, commands, and
      model-provided provisioning/approval fields.
- [ ] RED/GREEN: server-authenticated tenant/actor ownership checks for every
      catalog, profile, connection, session, alias, approval, and trace lookup.
- [ ] RED/GREEN: merge DAR capability inspection with wrapper capability checks;
      reject metadata-only or missing wrapper requirements before execution.

## G2: Fastmail Control Plane and Surface Binding

- [ ] RED: profile without an authenticated least-scope connection returns
      `authentication_required`.
- [ ] GREEN: human-only OAuth/API-token connection flow with secret storage
      outside package artifacts and immutable profile/scope binding.
- [ ] RED/GREEN: approved Fastmail surface snapshot creation/review plus passive
      `tools/list` identity/input-schema drift detection on the run path.
- [ ] RED/GREEN: construct host-authored, caller-supplied `MCPToolBinding`
      handlers only from an approved snapshot; fake Fastmail tests only.

## G3: Read-Only Workflow Runner

- [ ] RED/GREEN: select a strict local model adapter and reject hosted fallback.
- [ ] RED/GREEN: execute fake `list_unread` through approved profile bindings,
      merged preflight, bounded result shaping, and deep-redacted tracing.
- [ ] RED/GREEN: `--dry-run` validates catalog/profile/snapshot/path policy but
      invokes neither a model nor an MCP handler.

## G4: Trusted File Ingress

- [ ] RED: source files outside the configured caller input root, symlinks,
      devices, non-regular files, oversized content, invalid encoding, and
      parent-swap races are rejected.
- [ ] GREEN: use the sandbox specification's descriptor-relative no-follow
      primitive to copy the exact opened source into a fresh private workspace;
      return only virtual URI, hash, and byte count.
- [ ] RED/GREEN: prove physical paths and raw body content are absent from model
      inputs, tool results, traces, audit records, and approval displays.

## G5: Deterministic Write Workflow Runner

- [ ] RED: model-directed, undeclared, drifted, or over-cardinality writes fail
      before their external handler runs.
- [ ] GREEN: use wrapper-private bindings whose handlers verify catalog-exact
      argument projection, profile, snapshot, and G4 hash-bound file ingress.
- [ ] RED/GREEN: default `auto` records the canonical external action; `--ask`
      uses a short-lived, one-use, tenant/actor-bound atomic approval decision.
- [ ] RED/GREEN: changing the package revision, recipient alias, subject, body
      hash, profile, or snapshot invalidates an outstanding `--ask` decision.

## Deferred After the First Release

- [ ] Retrieval/embedding profiles and host vector/index services.
- [ ] Durable conversational sessions and durable DAR interruption continuation.
- [ ] Guardrail phases beyond DAR's live input and tool-input handlers, and
      broader context-management profiles.
- [ ] Subagent and `ask_llm` integration.

## Focused Validation

- [ ] All unit tests use fake model adapters, Fastmail handlers, approval stores,
      and filesystem primitives; no live Fastmail, Hugging Face, or model call.
- [ ] A positive fixture is required before a gate's capability is reported live.
- [ ] G5 may run only after G0–G4 pass; it must not replay a DAR approval
      interruption or claim graph-preserving continuation.
