<!-- markdownlint-disable MD013 -->
# Apple Foundation Models Adapter Implementation Plan

Status: A1 implementation complete; standalone eligible-Mac live paths verified; pytest-native SDK verification blocked

## Scope and authority

This plan implements A1 of `specs/apple-foundation-model-adapter/spec.md`: an
optional, lazy, macOS-only in-process adapter for final text and explicit JSON
Schema output. A2 Apple tool callbacks, approval coordination,
provider-native streaming, multimodal input, persistence, and HTTP serving are
not implementation targets here.

The existing `AsyncOpenAIClientAdapter` remains the executor-facing adapter.
The Apple provider implements `AsyncOpenAIClientProtocol` and returns the
Responses-shaped mapping consumed by the existing normalizer. No executor
branch, second provider framework, or `fmx` runtime dependency is allowed.

## Target surfaces

- New module: `src/dynamic_agent_runner/apple_foundation_models.py`
- Package exports: `src/dynamic_agent_runner/__init__.py`
- Existing seams: `src/dynamic_agent_runner/openai_client.py`,
  `src/dynamic_agent_runner/errors.py`, `src/dynamic_agent_runner/executor.py`
- Focused tests: `tests/test_apple_foundation_models.py`,
  `tests/test_executor.py`, `tests/test_import.py`
- Authored documentation: `README.md` or selected `docs/files/` source;
  never edit generated `docs/source/*.rst` directly.

## Proposed public contract

Define `AppleFoundationModelConfig` with caller-visible aliases (defaulting to
`("apple-system-language-model",)`), optional injected availability/session
factory collaborators for tests, and conservative generation settings. Define
`create_apple_foundation_model_async_adapter(config=..., ...)` returning the
existing `AsyncOpenAIClientAdapter` with `is_local=True`, Apple provider
metadata, and configured aliases. Exact field names may be finalized in RED
tests, but the public surface must remain limited to configuration and the
async factory described by the spec.

## Provider boundary

The Apple module owns lazy `apple_fm_sdk` imports, platform/version checks,
availability preflight, one fresh `LanguageModelSession` per request, message
translation, generation-option mapping, JSON Schema guided generation, and
package-owned error translation. SDK types must not escape the module. Injected
fakes must cover availability, session creation, generation, and SDK failures.

Use the existing `OpenAIModelRequest`, `ModelResponse`, adapter metadata, strict
coverage selection, and response normalization. Reject tools, tool transcript
items, non-text content, images/audio, streaming requests, schema-less JSON
object mode, conflicting token aliases, and unsupported generation options
before SDK invocation.

## Error and capability policy

Use `ModelExecutionError` (or a narrowly scoped Apple subclass only if tests
prove it is needed) with the SDK exception as `__cause__`. Preserve opaque
failures without inventing retry classification; do not add provider retries.
Advertise only local in-process execution, structured output, and final text:
streaming, tool calling, multimodal input, and embeddings remain false.

## Validation strategy

Unit tests are fake-backed and must run on every platform without importing the
optional SDK. Separate live tests are marked for eligible Macs and validate
real text, JSON Schema output, and a strict-coverage DAR workflow; they skip
with an actionable prerequisite reason when the SDK or system model is absent.
Run focused tests after each slice, then the full suite, Ruff, package checks,
and focused pre-commit. A1 is complete when deterministic tests, standalone eligible-Mac live paths, import portability, and documentation checks pass; pytest-native SDK verification is tracked separately as T6.6.

## Explicit non-actions

Do not implement A2 tool registration/coordinator wiring, add an HTTP endpoint,
vendor or invoke `fmx`, add a mandatory Apple dependency, alter default OpenAI
selection, or expose Apple SDK sessions/transcripts as DAR state.

## Post-implementation decision

Standalone runtime verification is accepted for A1 text, structured output, and strict workflow behavior. The pytest-native Apple SDK path remains blocked by repeatable native GenerationError status 255 behavior despite successful availability preflight; future work must isolate or replace that harness before using it as a release gate. No provider retry or pytest-specific runtime behavior is added from this evidence.
