# M6.4 Qwen3 MLX Manual Competency Validation

Date: 2026-09-11

## Scope

This is manual, local-only evidence for the explicit Qwen3 helper. It is not a
pytest, CI, release, arbitrary-model, or generic-MLX compatibility claim. Each
sample used DAR's in-memory controlled recording registry: no external tool,
account, endpoint, network request, or model download occurred.

## Provenance and Controls

- Host: macOS `26.6.2`, Darwin `arm64`; Metal execution required the approved
  host execution context rather than the filesystem sandbox.
- DAR source: `f60954e4f9de1043bc64be990aeac97d6a8bf9a2`, with the manual
  runner/test worktree diff SHA-256
  `1341c9b3016ba48e37d77ad5fb4e0c1514c49b055bdcf7e5717d2132013d348e`.
- Model repository and immutable revision:
  `mlx-community/Qwen3-4B-Instruct-2507-nvfp4` at
  `111ab717db337468c86004a79bd9df19c6e3986d`.
- Runtime: `mlx-lm 0.31.3`, `mlx 0.32.2`; codec
  `qwen3-mlx-tool-envelope-v1`.
- Controls: `S1`, synchronous mode, omitted `tool_choice`, fixed prompt digest
  `21baae6ccb718dc3f04bd1be7c29757db17a0cc03cf2a080629c86da27e2d4da`,
  seed `20260830`, temperature `0.0` through `make_sampler`, maximum `256`
  generated tokens, and a `120`-second per-scenario wall-clock deadline.
- The local snapshot directory was named `manual-matrix-20260830`, rather than
  the canonical revision directory. Its required six artifact file hashes match
  every entry in [`m6.4-compatibility-profile.md`](m6.4-compatibility-profile.md).
  This establishes content identity for these runs but does not claim that the
  directory itself satisfied a canonical default-Hub locator preflight.

## Recorded Outcomes

Every run selected the allowed `create_record` schema exactly once, executed
only the in-memory recording handler once, rendered its matching continuation,
and returned nonempty ordinary text. `tool_choice` was omitted in all cases.
The raw response text and handler payloads are intentionally not retained.

| Run ID | Outcome | Invocations | Initial raw SHA-256 | Continuation raw SHA-256 |
| --- | --- | ---: | --- | --- |
| `6e74ccde947a44d6bfd8d143a086541d` | passed | 1 | `37fb83f825f3de70647d23ec37d57e1f65996f051b2ee78c6451f5066ce15000` | `d0b4fad0b463edcad12b71e846983474ec8e8036653b85d8a63a87f1ca6e85a3` |
| `5746187029bd4af08c7ccd446ee9d5a3` | passed | 1 | `37fb83f825f3de70647d23ec37d57e1f65996f051b2ee78c6451f5066ce15000` | `d0b4fad0b463edcad12b71e846983474ec8e8036653b85d8a63a87f1ca6e85a3` |
| `4d22662927eb4aa0ae1f7465c03ae49e` | passed | 1 | `37fb83f825f3de70647d23ec37d57e1f65996f051b2ee78c6451f5066ce15000` | `d0b4fad0b463edcad12b71e846983474ec8e8036653b85d8a63a87f1ca6e85a3` |

The observed rate was 3/3 successful bounded pairs. Matching digests are an
observation under these controls, not a promise of model determinism.

## Runner Correction

The first manual attempt exposed that `mlx-lm 0.31.3` does not accept a direct
`temperature` generation keyword: it ended as an `adapter_error` with no tool
invocation. The runner now seeds MLX explicitly and supplies temperature
through `mlx_lm.sample_utils.make_sampler`; it records the fixed controls,
per-scenario deadline, error category, and raw-output digests. Focused
fake-only tests cover those receipt boundaries. The three successful runs above
used that corrected runner.

## Final Repository Validation

- `poetry run pytest -q`: passed (`2290 passed, 1 skipped, 7 deselected`).
- `poetry run ruff check src tests scripts`: passed.
- `poetry run ruff format --check src tests scripts`: passed (`270 files
  already formatted`).
- `poetry run pre-commit run --files <changed files>`: passed (Ruff and
  Markdown hooks; nonmatching YAML, JSON, and TOML hooks skipped).
- `poetry run make -C docs html`: passed. The generated Python API source and
  rendered HTML were regenerated and reviewed without hand-editing
  `docs/source/*.rst`.
