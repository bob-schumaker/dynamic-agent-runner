# Sealed Artifact Workflow Runner Plan

## Objective

Finish the domain-neutral DAR receiver so a locally authorized sealed workflow
package can transform declared opaque input-artifact handles into declared
opaque output-artifact handles through one verified asset ABI and only declared,
bounded host callbacks. Prove the required admission order at real host
boundaries, then migrate the embedding-index and locked-inference consumers so
neither retains a parallel asset-execution or artifact-egress route.

## Current state

The approved v1 contract in `spec.md` is implemented through the host-owned
composition boundary:

- canonical descriptor, manifest, schema, child-contract, and capability
  binding validation;
- provenance-bound preparation, opaque input-handle reservation and consumption,
  import-disabled `run(context)` execution, bounded callbacks, and ordered
  private output collection;
- atomic output-handle publication, cancellation/revocation, deadline and I/O
  enforcement, and redacted receipts; and
- `LocalWorkflowHost` composition with explicit callback resolution.

S1 through S5 are complete. The S2 admission sentinels now observe actual
package/ZIP, input-byte, callback-provider/material, output-publication, and
egress boundaries. The embedding-index and locked-inference consumers now use
the same generic runner, so neither retains a parallel asset-execution or
artifact-egress route.

## Boundaries and decisions

This plan owns the outer sealed-artifact descriptor, invocation lifecycle,
asset ABI, generic callback controls, and output sealing. It does not add
document, vector-index, clustering, tag, prompt, model, provider, filesystem,
or output-destination semantics to DAR.

The production runner remains the only asset execution route. Test observers
may wrap real collaborators, but they are not a public plugin API and must not
become a second generic admission pipeline. Asset code continues to receive
only `read_input`, `invoke_callback`, declared-callback `callback_identity`,
and `write_output`; it cannot receive
host paths, raw handle records, capability objects, provider identities, or
unsealed collector/output bytes.

`callback_identity` exposes only the exact asset/child-contract identity and
its canonical digest for an already declared callback. It is not descriptor
introspection or a provider/material surface; it lets an asset bind output
metadata without an impossible self-digest literal.

The experimental personal profile is not an isolation claim. It admits only a
locally selected owner package with exact registration, revision, asset, and
profile authorization. Foreign or untrusted asset admission remains deferred
to the approved `local-tool-sandbox-hardening` backend already named by the
specification.

## Milestones

### M1 — Prove real admission boundaries (S2 remainder)

**Depends on:** completed S1, S3, and S4.

**Deliverable:** event-recording wrappers around the actual receiver
collaborators, plus focused negative and successful-invocation tests.

1. Add one test-only observer for each real effect that the runner can reach:
   registration/provenance resolution, catalog revision and manifest/descriptor
   reads, identity/capability resolution, input-handle reserve and byte
   consumption, callback-provider revalidation, material load/provider entry,
   collector seal, output-handle publication, and caller-authorized egress.
   Use wrappers around the existing services; do not duplicate their behavior.
2. Add one failure vector per admission boundary. Each vector asserts its stable
   redacted public classification and the complete zero-call suffix: after a
   failure, no subsequent real collaborator may be entered. In particular,
   verify that a package or descriptor failure performs no input byte access;
   a handle failure performs no asset or callback work; a callback/provider
   failure publishes or exports nothing; and a seal/publication failure has no
   egress.
3. Add a successful deterministic package fixture that uses actual staged
   package/manifest files, one prepared handle, and a declared output. Assert
   the exact observed order without inspecting raw private candidate bytes.
4. Cover failure cleanup through the same observers: reserved-but-unconsumed
   inputs are revoked, late or failed callback work cannot seal outputs, and no
   output handle exists until all slots have been atomically sealed.

**Acceptance:** the S2 subtask is checked only when the real collaborator
event log—not an internal asset-runtime fake—proves every fixed admission
boundary and its zero-side-effect suffix.

**Verification:**

```text
poetry run pytest tests/test_sealed_artifact_runner_admission.py \
  tests/test_sealed_artifact_workflow_runner.py \
  tests/test_dar_authoring_host.py -q
poetry run ruff check src tests
```

### M2 — Complete locked-inference receiver admission (dependency I2)

**Depends on:** locked-inference I1. This work may proceed independently of M1,
but M3 cannot begin until I2 is green.

**Deliverable:** locked-inference policy admission verifies exact instruction
and schema bytes/digests before package asset import, model material loading,
or provider entry; the callback preserves exact-role no-fallback semantics.

The locked-inference specification owns this work. This plan consumes only its
published child-contract and callback-provider interface. The sealed runner
must not duplicate role parsing, material binding, schema interpretation, or
provider selection.

**Acceptance:** I2's fake-only policy and execution suites prove asset-digest
binding, role isolation, host ceilings, concurrency, revalidation, redaction,
and zero later side effects. Its tasks are marked green in the owning spec.

### M3 — Define consumer descriptors through the generic runner (S5 design)

**Depends on:** M1, M2, and embedding portable runtime E6.

**Deliverable:** one package fixture per consumer using only
`sealed-artifact-runner.json`, normal package manifest registration, declared
artifact roles, capability requirements, child-contract digests, and the fixed
asset ABI.

1. Map each embedding input/output and locked-inference callback to the generic
   descriptor fields. Keep consumer payload semantics inside its child contract
   or sealed asset; the outer descriptor stores only the generic role, media,
   schema digest, limits, capability requirement, and callback bounds.
   The embedding fixture declares required JSON `snapshot` input, optional
   opaque `prior_bundle` and JSON `prior_index_manifest` inputs as one pair,
   and the lexical output triple `coverage_report` (JSON), `index_bundle`
   (opaque bytes), and `index_manifest` (JSON). It declares only the exact
   `embed` callback requirement. The runner does not interpret the paired
   inputs or the output payloads beyond their generic contracts.
2. Bind the existing `embedding.execute.v1` and `model.generate.v1` contracts
   through the callback table. A sealed asset may invoke only the callback
   declared for its exact child contract; it cannot select a provider, model,
   material, executable, endpoint, or destination.
3. Establish source-level bypass tests before migration. They must fail if a
   consumer directly imports an asset, reads an invocation path, creates an
   output/result artifact, or enters a provider outside the generic runner.

**Acceptance:** both fixture descriptors register, prepare, and execute using
the same generic receiver API without scenario-specific DAR source.

### M4 — Migrate the embedding-index consumer (S5a)

**Depends on:** M3 and E6 completion.

**Deliverable:** the embedding package executes its sealed index-builder asset
through the generic runner and returns exactly three declared physical output
handles: `coverage_report`, `index_bundle`, and `index_manifest`. The bundle
and manifest are one logical index-bundle result; the report is the other
logical result.

1. Replace the host-private embedding builder bridge with the sealed asset
   fixture and generic invocation/preparation calls.
2. Preserve the embedding spec's snapshot, paired prior-bundle and
   prior-index-manifest, material, deterministic-batch, index-bundle,
   index-manifest, and coverage-report validation in their owners. The runner
   validates only generic descriptor/handle/ABI rules. The consumer validates
   the manifest's `bundle_sha256` against the opaque `index_bundle` bytes and
   validates the common invocation bindings before publication.
3. Add fake-only end-to-end coverage for initial and paired-prior-bundle runs,
   exact callback binding, atomic egress, a bundle/manifest digest mismatch,
   and source-data/vector redaction. A mismatch publishes or exports no
   output handles.
4. Delete the replaced direct builder/import/egress route and its bypass tests
   in the same change. Do not leave a compatibility switch.

**Acceptance:** package export, registration, prepared snapshot input, callback
execution, and atomic opaque publication of the required output triple all
traverse the sealed runner; a source-level test finds no remaining
embedding-specific host invocation route.

### M5 — Migrate the locked-inference consumer (S5b)

**Depends on:** M3 and M2. M5 is independent of M4 and may run in parallel
with it only after M3 establishes separate fixtures and no shared production
files are edited concurrently.

**Deliverable:** a callback-enabled asset receives the exact private
locked-inference provider only through the sealed-runner callback adapter and
writes declared result slots through its collector.

1. Bind inference-role child contracts and their exact capability requirements
   to the outer descriptor callback records.
2. Run fake-only admission, role-isolation, quota, deadline, cancellation,
   late-result-disposal, and atomic-output tests through the generic receiver.
3. Delete the old direct callback-enabled asset route after its sealed
   replacement passes; retain no fallback to the old entry point.

**Acceptance:** no locked-inference package asset can reach a provider or
result artifact except through the generic sealed runner, and ordinary receipts
remain limited to digests, counts, and stable classifications.

### M6 — Integration and release evidence

**Depends on:** M4 and M5.

Run consumer-focused suites first, then the full regression, lint, and build:

```text
poetry run pytest tests/test_sealed_artifact_runner_admission.py \
  tests/test_sealed_artifact_workflow_runner.py \
  tests/test_locked_inference_execution.py \
  tests/test_workflow_locked_inference.py -q
poetry run pytest -q
poetry run ruff check src tests
poetry build
```

The migration gate fails on any raw artifact data in a receipt, any output
allocation before atomic seal, a live-model/network/tool dependency in tests,
or any retained consumer bypass.

## Work-package dependency matrix

| Work package | Depends on | Owns | Completion evidence |
| --- | --- | --- | --- |
| S2-real | S1/S3/S4 complete | real-collaborator sentinels | event logs prove boundary and zero-call suffix |
| I2 | locked-inference I1 | role asset/policy admission | owning focused RED/GREEN tests pass |
| E6 | embedding E1–E5 | portable embedding package runtime | owning ZIP/descriptor tests pass |
| S5-design | S2-real, I2, E6 | generic consumer descriptor fixtures | both consumers register through one ABI |
| S5-embedding | S5-design, E6 | embedding migration and deletion | no direct builder route remains |
| S5-inference | S5-design, I2 | inference migration and deletion | no direct callback asset route remains |
| S5-integration | S5-embedding, S5-inference | regression/release evidence | full test, lint, and build pass |

## Risks, rollback, and cleanup

| Risk | Trigger | Control | Rollback / stop condition |
| --- | --- | --- | --- |
| A sentinel observes a mock, not the host boundary | a negative test passes while a real service could still act | wrap real collaborators and assert ordered events | keep S2 open; add the missing observer |
| Consumer semantics leak into DAR | a migration adds chunk, tag, prompt, or vector logic to host source | confine semantics to sealed asset/child contract | reject the change and revise the consumer descriptor |
| Migration retains an unsealed escape hatch | an old route still imports assets, calls providers, or publishes outputs | add source-level bypass tests and delete old route atomically | retain the old path only until its sealed replacement has passed; do not expose selection |
| Experimental profile is treated as untrusted isolation | a foreign package is admitted | exact local-owner authorization and profile verification | reject admission; await `local-tool-sandbox-hardening` |
| Consumer prerequisite changes outer ABI | I2 or E6 needs a generic field not represented by the descriptor | add a RED sealed-runner contract vector first | return to S1 contract review; do not add a consumer-specific side channel |

Rollback is additive until a consumer's legacy route is deleted. If migration
reveals a missing generic field, restore the previously passing host-private
consumer path with no public selector, retain the new sealed route disabled,
amend the approved outer contract, and repeat the admission vectors before
trying the migration again. Never relax authorization, output-sealing, or
untrusted-asset isolation requirements as a migration workaround.
