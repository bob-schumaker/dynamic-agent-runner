# MLX GTE Tiny MLE6 Approval

Decision date: 2026-09-13

## Approved closure

- Package ID: `mlx-gte-tiny-embedding-v1`
- Source: `TaylorAI/gte-tiny`
- Revision: `4cc5e73d86a67c601897257b467187234aa3bca3`
- Required files: the exact ten source files and SHA-256 values in the adjacent
  `model-material-lock.json`; a receiver may use its cached copy only when every
  value matches.
- Expected descriptor ABI:
  `bert-encoder-mlx-v2@2` with contract digest
  `646e958aae4752c3fdb2503d257929b95ad037c5462a35a7fa9e5d23aa14d35d`.

## License decision

The upstream repository does not declare a license in its Hub metadata. The
approver authorizes this exact cached closure only for local, internal
conformance and integration testing. This decision does not authorize
redistribution, publication, or a claim of an upstream SPDX license.

## Requested execution ceilings

| Limit | Value |
| --- | ---: |
| Items and vectors per request | 16 |
| Bytes per item | 64 KiB |
| Aggregate input bytes | 1 MiB |
| Tokens per item | 512 |
| Tokenizer bytes | 1 MiB |
| Weight bytes | 64 MiB |
| Safetensors header bytes | 1 MiB |
| Conformance fixture bytes | 1 MiB |
| Process memory | 128 MiB |

The future v2 material lock and descriptor must bind these values. This record
does not authorize a download, reference-vector generation, MLX execution, or
support-matrix admission; those remain MLE6.2--MLE6.6 gates.
