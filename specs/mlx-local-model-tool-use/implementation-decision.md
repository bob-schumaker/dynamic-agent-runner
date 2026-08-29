# MLX Tool Codec Implementation Decision

Status: accepted
Date: 2026-08-28

## Decision

DAR's first built-in in-process MLX tool codec targets the Qwen3 Instruct
model family and its native tool-aware chat template. The parity-suite model
artifact is `mlx-community/Qwen3-4B-Instruct-2507-nvfp4`, pinned to Hugging
Face revision `111ab717db337468c86004a79bd9df19c6e3986d` (2.28 GB, Apache-2.0).
This is a small, local, 4-bit Qwen3 Instruct artifact selected to exercise the
same controlled-tool parity cases as other DAR model interfaces.

The implementation uses the released `mlx-lm` Python package, constrained to
`>=0.31.3,<0.32.0`. Its authoritative upstream source is
[`ml-explore/mlx-lm`](https://github.com/ml-explore/mlx-lm), release `v0.31.3`,
at immutable commit [`ed1fca4`](https://github.com/ml-explore/mlx-lm/commit/ed1fca4).
The locked distribution is `mlx_lm-0.31.3-py3-none-any.whl` with SHA-256
`758cfddf1180053b7613db76fad3d246a331a2a905808e1164a275621fc983b8`.
DAR does not vendor an upstream source subproject.

## Compatibility Contract

At model load, the built-in codec must use the tokenizer's native
`apply_chat_template(messages, tools=..., add_generation_prompt=True)` path.
It must require a chat template, advertised tool-calling support, and a
declared tool parser before reporting `tool_calling=True`. The exact parser is
discovered from the selected tokenizer at runtime; DAR must not hard-code an
unverified Qwen syntax.

The codec translates that native rendering and parsed result into DAR's
existing strict, one-call `ModelToolCall` contract. It retains the current
bounded, duplicate-safe JSON normalization and all existing DAR execution
controls. A tokenizer that fails these runtime gates remains text-only.

## Provenance and Update Policy

The Qwen base model card identifies Qwen3 as supporting tool calling and
agentic use; the selected MLX conversion preserves a repository-local pinned
artifact revision. The upstream `mlx-lm` release includes the server-side tool
call support used as API evidence, but DAR relies only on its in-process
tokenizer/template and parser interfaces.

Keep the current `>=0.31.3,<0.32.0` compatibility line until an explicit
decision updates it. Any upgrade must inspect the tokenizer/template and parser
interfaces, rerun the deterministic codec and parity tests, record a new
immutable source revision and lock hashes, and update this decision. Optional
manual competency runs occur only on an eligible Apple Silicon host and never
become pytest or CI dependencies.

## Sources

- [Qwen3-4B model card](https://huggingface.co/Qwen/Qwen3-4B)
- [Selected MLX artifact revision](https://huggingface.co/mlx-community/Qwen3-4B-Instruct-2507-nvfp4/tree/111ab717db337468c86004a79bd9df19c6e3986d)
- [`mlx-lm` v0.31.3 release](https://github.com/ml-explore/mlx-lm/releases/tag/v0.31.3)
