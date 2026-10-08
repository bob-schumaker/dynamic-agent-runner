<!-- markdownlint-disable MD013 -->
# DAR External Adapter Protocol Tasks

Status: implemented; validation recorded in `validation.md`

## Authority and execution rules

- Spec: [`spec.md`](spec.md), status `approved`
- Plan: [`plan.md`](plan.md), status `approved`
- Implementation is limited to the Chrome v1 slice.
- Use fake adapters and fake browser bridges; no live provider calls in unit
  tests.
- For each implementation task, write or update the focused RED test first,
  observe the expected failure, implement the smallest change, then rerun the
  focused test before moving on.
- Do not add multimodal, streaming, persistent-session, native-callback,
  AFM/Ollama, marketplace, or per-node-binding work.

## Slice 1 — Contract RED tests

Dependencies: none

- [x] T1.1 Create `tests/test_external_adapter_protocol.py` with import tests
      for the public protocol, descriptor, health, context, cancellation, and
      package-owned error exports.
- [x] T1.2 Add RED descriptor tests for protocol/version mismatch, missing or
      unknown fields, invalid text-only capability values, invalid limits,
      duplicate identities, and invalid contract digests.
- [x] T1.3 Add RED canonical digest vectors proving the digest excludes its own
      field, is deterministic, rejects tampering, and freezes retained
      descriptor state.
- [x] T1.4 Add RED request/response tests for ordered messages, text-only v1,
      JSON Schema validation/canonicalization, `raw=None`, redacted metadata,
      malformed responses, and package-owned errors.
- [x] T1.5 Add RED context tests proving the adapter receives only
      `DARExternalRequestContext` with no handler or approval reference, plus a
      handler-spy test proving only a returned `ModelToolCall` reaches the
      existing coordinator.

Verification:

```text
poetry run pytest tests/test_external_adapter_protocol.py -q
```

Expected initial result: the new tests fail because the protocol module and
exports do not yet exist.

## Slice 2 — Protocol types and validation

Dependencies: T1.1–T1.5

- [x] T2.1 Add `src/dynamic_agent_runner/external_adapter.py` with
      `DARExternalAdapterProtocol`, descriptor, health, request context,
      cancellation handle, and package-owned errors.
- [x] T2.2 Implement protocol/version, finite-capability, text-only modality,
      limits, and response-format validation at the public boundary.
- [x] T2.3 Implement canonical descriptor digest calculation and defensive
      immutable copies without exposing transport, credential, or vendor data.
- [x] T2.4 Implement response normalization, JSON Schema validation, metadata
      redaction, and cancellation/error translation using existing DAR response
      shapes.
- [x] T2.5 Turn the Slice 1 tests GREEN and add regression cases for every
      rejected descriptor/request shape discovered during implementation.

Verification:

```text
poetry run pytest tests/test_external_adapter_protocol.py -q
```

## Slice 3 — External adapter façade and dispatch

Dependencies: T2.1–T2.5

- [x] T3.1 Add the DAR-owned façade that implements the existing `ModelAdapter`
      seam with `models=(descriptor.model_alias,)` and descriptor-derived
      metadata.
- [x] T3.2 Add the shared bounded external-adapter dispatcher for sync calls
      from async workflows, including bounded admission, deadline, cancellation,
      and shutdown behavior.
- [x] T3.3 Reject sync invocation of an async-only descriptor before adapter
      invocation; await async results and reject invalid awaitables for sync
      mode.
- [x] T3.4 Add internal single-use dispatch-token state for forged, expired,
      revoked, adapter/digest/model/mode-mismatched, and replayed calls. Keep
      the token private; do not export a lease protocol.
- [x] T3.5 Add element-wise normalization at `_normalize_model_adapters` so a
      raw external protocol object is wrapped before legacy selection whether
      supplied alone, inside a sequence, or in a mixed external/legacy sequence.
- [x] T3.6 Turn façade and dispatcher tests GREEN, including worker saturation,
      deadline, cancellation, mixed-sequence, and context-isolation cases.

Verification:

```text
poetry run pytest tests/test_external_adapter_protocol.py tests/test_executor.py -q
```

## Slice 4 — Receiver registry and persistence

Dependencies: T2.1–T3.6

- [x] T4.1 Add `src/dynamic_agent_runner/workflow_host/external_adapter_registry.py`
      for receiver-owned install, remove, list, exact resolution, and façade
      creation.
- [x] T4.2 Validate static metadata before factory import; reject unapproved
      packages, URLs, duplicate IDs, protocol mismatches, and unsupported
      descriptors. Use a sentinel factory/module to prove malformed,
      unapproved, tampered, and artifact-trust failures do not import or
      execute factory code during install.
- [x] T4.3 Persist only the receiver receipt under the DAR state root with
      owner-only permissions and atomic replacement. Include adapter ID,
      protocol/version, descriptor digest, artifact digest or trusted
      signer/origin, factory reference, immutable `artifact_locator`, and
      distribution name/version.
- [x] T4.4 On process reload, revalidate the receipt, locator, exact artifact
      bytes, and trust metadata before importing the factory; then import the
      validated factory and revalidate the live descriptor. Disable changed,
      missing, deleted, moved, replaced, or factory-mismatched registrations at
      either stage.
- [x] T4.5 Make removal revoke pending calls, preserve already-dispatched work,
      and remove only the registration record.
- [x] T4.6 Add registry tests for exact tuple resolution, duplicate aliases,
      health gating, receipt rollback, permissions, restart revalidation, and
      asset/cache preservation. Prove failed atomic receipt replacement leaves
      no partially trusted registration and that reload never imports a
      changed, deleted, moved, replaced, or factory-mismatched artifact.

Verification:

```text
poetry run pytest tests/test_external_adapter_protocol.py -q
```

## Slice 5 — Executor selection and capability admission

Dependencies: T3.5–T4.6

- [x] T5.1 Integrate receiver-created façades through the existing
      `model_adapter` path without adding a Chrome-specific executor branch or
      changing the public API/context shape.
- [x] T5.2 Make descriptor-derived capabilities and limits authoritative before
      ordinary fallback selection; reject unsupported structured output,
      tool-calling, model semantics, or limits before external dispatch.
- [x] T5.3 Make a selected external adapter constrain the whole workflow to its
      sole model alias. Reject any mismatched LLM node before default OpenAI
      construction or dispatch under both strict and augmented policies.
- [x] T5.4 Resolve an omitted model alias to the selected external descriptor's
      sole alias; reject ambiguous or multiple external selections.
- [x] T5.5 Route model-returned `ModelToolCall` values through the existing
      coordinator and prove the external adapter never receives a handler or
      approval object.
- [x] T5.6 Add RED/GREEN coverage in `tests/test_executor.py` for direct raw
      BYOM injection, selected receiver façades, strict/augmented coverage,
      alias collisions, capability admission, multi-node mismatch, no fallback,
      and unchanged OpenAI/LiteLLM behavior.

Verification:

```text
poetry run pytest tests/test_executor.py tests/test_openai_client.py -q
```

## Slice 6 — CLI lifecycle

Dependencies: T4.1–T4.6

- [x] T6.1 Extend `src/dynamic_agent_runner/cli.py` with:
      `adapter install <approved-local-plugin>`, `adapter remove <adapter-id>`,
      and `adapter list`.
- [x] T6.2 Add receiver-owned `--state-root` handling for adapter lifecycle
      commands without changing ordinary workflow invocation.
- [x] T6.3 Add CLI tests for parser dispatch, successful install/list/remove,
      duplicate/invalid package failure, redacted errors, transactional
      rollback, and process-reload behavior.

Verification:

```text
poetry run pytest tests/test_cli.py -q
```

## Slice 7 — Public exports and documentation

Dependencies: T2.1–T5.6

- [x] T7.1 Export the approved protocol, descriptor, health, request context,
      cancellation handle, normalized types, and package-owned errors from
      `src/dynamic_agent_runner/__init__.py`.
- [x] T7.2 Add the minimum `README.md` usage documentation for receiver-approved
      installation, direct BYOM injection through `model_adapter`, text-only v1
      limits, fail-closed behavior, and the tool boundary.
- [x] T7.3 Add import and documentation checks; do not document deferred
      transports or migrations as implemented.

Verification:

```text
poetry run pytest tests/test_import.py -q
poetry run ruff check src tests
```

## Slice 8 — Optional Chrome bridge

Dependencies: T2.1–T5.6, T6.1–T7.3

- [x] T8.1 Add the separately packaged Chrome adapter entrypoint depending only
      on the exported protocol and browser bridge. The first artifact target is
      `plugins/dar-chrome-external-adapter/` with its own `pyproject.toml`,
      distribution name `dar-chrome-external-adapter`, static manifest
      `dar_external_adapter.json`, and factory entrypoint
      `dar_chrome_external_adapter:create_adapter`. The manifest and receipt
      must provide the immutable artifact locator and digest consumed by
      `adapter install`.
- [x] T8.2 Implement supported Chrome Built-in AI text and structured-result
      translation with readiness/download health reporting. Assert the
      descriptor exposes exactly one text alias, text-only v1 capabilities, and
      excludes `tool_calling`; streaming and native callbacks are unsupported
      v1 semantics and must be rejected at admission rather than represented as
      descriptor fields.
- [x] T8.3 Authenticate extension/origin identity, bind requests to the DAR
      context, enforce size/deadline limits, and reject disconnect/replay cases.
- [x] T8.4 Add fake bridge conformance tests for unavailable Chrome/API/model,
      malformed results, cancellation, deadline, and session loss. Include
      wrong/untrusted extension or origin identity, missing/wrong DAR context
      binding, replayed requests, and post-disconnect requests; assert no
      browser call occurs when readiness is unavailable.
- [x] T8.5 Add an end-to-end fake test that installs the package artifact,
      reloads the registry in a fresh process boundary, validates the receipt,
      creates the receiver façade, and executes one fake bridge response.
- [x] T8.6 Build the plugin from `plugins/dar-chrome-external-adapter/`, run its
      package-local import/conformance tests, and inspect the built artifact to
      prove that `dar_external_adapter.json` and
      `dar_chrome_external_adapter:create_adapter` are packaged and discoverable
      by the receiver installer. Add a deterministic
      `scripts/verify_built_artifact.py --dist dist` check for the wheel contents
      and factory entrypoint.

Verification:

```text
poetry run pytest tests/test_external_adapter_protocol.py -q
# From plugins/dar-chrome-external-adapter/
poetry run pytest -q
poetry build
poetry run python scripts/verify_built_artifact.py --dist dist
```

Live Chrome validation is a separately authorized integration gate and is not
part of the unit-test command.

## Slice 9 — Completion gate

Dependencies: T1.1–T8.6

- [x] T9.1 Run focused protocol, executor, CLI, import, fake bridge, and
      install→reload→façade composition tests, including the plugin-package
      import/conformance tests.
- [x] T9.2 Run the full test suite and Ruff.
- [x] T9.3 Run `poetry check`, the root `poetry build`, the plugin-package
      `poetry build`, and `git diff --check`; verify the plugin build contains
      its manifest and factory entrypoint with
      `poetry run python scripts/verify_built_artifact.py --dist dist` and run
      the plugin's `poetry run pytest -q` before accepting the root gate.
- [x] T9.4 Create `validation.md` with exact commands, observed results,
      acceptance traceability, deferred-scope checks, and any separately
      authorized Chrome evidence; review spec/plan/tasks consistency against it.
- [x] T9.5 Confirm deferred multimodal, streaming, native-callback, AFM,
      Ollama, marketplace, and per-node-binding work remains unimplemented.

Verification:

```text
poetry run pytest -q
poetry run ruff check src tests
poetry check
poetry build
git diff --check
```

## Deferred work

Do not create tasks for multimodal/streaming/native-callback protocol versions,
AFM/Ollama/vLLM/MLX/llama.cpp service migrations, richer provider registries,
compatibility wrappers, or a separate BYOM conformance suite until a concrete
second implementation receives a new approved slice.

## Readiness

This plan is ready to execute under its stated gates. Implementation must use
the RED/GREEN sequence above and update task status with exact validation
evidence.
