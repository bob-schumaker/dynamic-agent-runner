# Workflow Input Converter Plugin Validation

## Current delivery boundary

The converter delivery path is a sealed Python package loaded through the
manifest-bound standard converter interface. Package identity, entry point,
compatible runner contract, and resource declarations are validated at
registration; prompt and payload bytes cannot choose or replace them.

The current feature does not claim OS isolation from malicious converter code.
Docker, `sandbox-exec`, and other full-isolation backends are future work under
[`../local-tool-sandbox-hardening/spec.md`](../local-tool-sandbox-hardening/spec.md).
Their existing probe evidence is recorded in
[`../local-tool-sandbox-hardening/validation.md`](../local-tool-sandbox-hardening/validation.md).

## Validation evidence and remaining work

T1 through T4 and T5.1--T5.4.4 are implemented. The focused fake-only suites
cover manifest binding, exact package entry-point loading, opaque packed-input
handoff and disposal, redacted failures, JSON constraint capability checks,
bounded continuation, and workflow-local JSON admission and SVG rendering.

On 2026-09-08, the explicitly authorized floorplan run
`22a6d05c-5fc9-4f73-a55d-65ff82510672` completed. Its retained raw completion
digest `542480e5b328509e60c0552c01806cc2afb8769bff63c4f3f6a0babc8409f57f`
was admitted as `189d07a5449fe548c2ad7559f93f541e79d92be2807e72eef1eafbed8a3f41e0`
with `none,none` processor reports, then returned validated SVG. This satisfies
the manual T5.5 gate without exposing the completion content.

The 2026-09-08 readiness validation ran:

- `poetry run pytest tests/test_qwen25_vl_3b_grpo_converter.py -q`: passed —
  `7 passed`; the floorplan package prompt assertion now locks the declared
  detailed JSON contract.
- `poetry run pytest -q`: passed — `1915 passed, 1 skipped, 7 deselected`;
  the seven warnings are the existing unregistered `live_matrix` marks.
- `poetry run ruff check src tests`: passed.
- `git diff --check`: passed.

T5.4.5 is complete. T5.6 may update feature status and prepare a release when
its release requirements are satisfied. The current local `0.1.19` sdist and
wheel have passed the package-integrity checks used by the release-contract
tests; this is local package evidence only. On 2026-09-18, the configured
`global-release-pypi` Simple index independently listed these `0.1.19`
artifacts:

- wheel SHA-256:
  `d8754c9c8ab8987750ae27a8373f156a1d80a8e5cec58148688826ef55b90fe7`
- sdist SHA-256:
  `9f7e01b4282c2570b67903a361b4cddd21f7bf686ae3b1ae42bfafc53046b735`

The index entry is not a release receipt for this feature. T5.6.2 is now
complete: the same index was queried on 2026-09-18, `0.1.19` was the latest
published version, and the next version was computed as `0.1.20`. The local
`0.1.20` artifacts passed the focused release-contract tests with these
SHA-256 values:

- wheel: `cc96f92bef46f267854adcfbc500c76735a4a2208acd489fb7c751b33012a9d4`
- sdist: `7d2edc1948e7a23b22a140ad0a8e6b18e06425b7022a4dc34b1028af0244a4cb`

Release delivery remains open until the repository-driven OCI workflow completes:
push the versioned commit to `develop`, complete the
DevOps SCM pull request, merge to `main`, wait for the main-branch build, and
then record the resulting package-index evidence and release receipt. Repository
tags already reach `0.1.31`, so `0.1.19` must not be silently reused as the next
release. The Mac-only
T5.7.1--T5.7.2 fake-only verification passed
on 2026-09-08:
`poetry run pytest tests/test_transformers_peft_model.py -q` reported
`35 passed`. It covers unchanged non-MPS loading, adapter-before-MPS placement,
evaluation mode, inference-only generation, and redacted MPS generation metadata
for direct and continuation responses. The corresponding full suite then passed:
`1917 passed, 1 skipped, 7 deselected`; the seven warnings remain the existing
unregistered `live_matrix` marks. This Apple M3 Pro host is MPS-capable. Inside
the Codex-restricted shell, PyTorch 2.13.0 reports MPS unavailable and emits a
misleading macOS-version error; the same environment outside that shell reports
`mps_built=True`, `mps_available=True`, and successfully allocates an MPS tensor.
The benchmark must therefore execute outside the restricted shell. No fallback
was enabled during this diagnosis. A current-MPS workflow attempt loaded the
prepared model but did not complete its first warm pass at the production
`4096`-token limit within five minutes, so it was terminated without retaining
benchmark metrics. The authorized replacement used a fixed `1024`-token,
zero-continuation limit and reached the terminal contract. With the same
prepared model, sealed image, and prompt, resident warm MPS measurement recorded
the prior loader order at 994 generated tokens in 167.301665 seconds (5.941363
tokens/sec), and the adapter-before-placement candidate at 994 tokens in
156.223020 seconds (6.362699 tokens/sec). The candidate is a 7.1% improvement
and preserves the terminal contract. No dtype or compilation experiment was
adopted; the current MPS configuration remains. OS-level isolation remains
deferred future hardening, not a converter-admission or release-validation
blocker.

T5.8 is complete. The host-owned diagnostic surface uses the authenticated
local principal, a separate diagnostic ID, an 8 MiB aggregate retained-artifact
limit, seven-day TTL, and owner-only revocation. Focused fake-only diagnostics
tests cover ordered fragment capture, post-generation failure and cancellation,
normal-trace redaction, aggregate limiting, revocation, and expiry; the adapter
test covers recording a malformed chunk before strict JSON rejection. On
2026-09-08 the explicitly authorized cleaned Japan-home MPS debug run retained
diagnostic `37196299-5c25-45de-bbe5-08abb15a6957` and classified it as failed:
three chunks reported generated-token counts `1024,19,19`, exhaustion states
`true,false,false`, malformed assembled JSON, no terminal processor reached,
and no retention-limit flag. The ordinary trace remained failed with zero output
bytes. No retained fragment content is recorded here. Final verification:
`poetry run pytest -q` reported `1926 passed, 1 skipped, 7 deselected`; `poetry
run ruff check src tests` and `git diff --check` passed. The seven warnings are
the existing unregistered `live_matrix` marks.
