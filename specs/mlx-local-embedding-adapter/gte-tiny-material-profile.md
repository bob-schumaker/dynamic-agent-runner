# GTE Tiny Locked Material Profile

This is construction-time evidence for the closed `mlx-gte-tiny-v1` profile.
It is not a model cache, package payload, or permission to download weights.

## Closed identity

The profile accepts exactly this predicate:

- logical model ID: `mlx-gte-tiny-v1`;
- runner contract: `mlx-gte-tiny-v1` version `1`;
- loader profile contract: `mlx-gte-tiny-v1` version `1`;
- source repository: `TaylorAI/gte-tiny`;
- source revision: `4cc5e73d86a67c601897257b467187234aa3bca3`; and
- the ten role/path/size/hash entries below, with no preparation operation.

The human-readable generic lock source fixture is
`tests/fixtures/mlx-gte-tiny/model-material-lock.json`; parsing its raw bytes
produces canonical lock digest
`c2fc8b91d1b4514f2411f30c4d81fa3a702e902b70ae8a7eb83567696a158c87`.
`tests/fixtures/mlx-gte-tiny/profile.json` is the machine-readable closed
profile table. Its role/path/hash/byte identity must match the lock before the
profile validator parses assets. It does not add GTE-specific fields to the
generic material-lock format.

| Role | Relative path | Exact bytes | SHA-256 |
| --- | --- | ---: | --- |
| `bert_config` | `config.json` | 669 | `d3e8bc1261c0933b87dfaa12e984e311158a723c5593a0a57f9558f2a8262e3c` |
| `bert_weights` | `model.safetensors` | 45,457,576 | `41282c37ddd19dbf7352fca3bafd3d187baffacd7231f3f0cd69b7525630e08d` |
| `modules_manifest` | `modules.json` | 229 | `8f4b264b80206c830bebbdcae377e137925650a433b689343a63bdc9b3145460` |
| `pooling_config` | `1_Pooling/config.json` | 190 | `4be450dde3b0273bb9787637cfbd28fe04a7ba6ab9d36ac48e92b11e350ffc23` |
| `sentence_transformer_config` | `sentence_bert_config.json` | 53 | `ec8e29d6dcb61b611b7d3fdd2982c4524e6ad985959fa7194eacfb655a8d0d51` |
| `tokenizer_added_tokens` | `added_tokens.json` | 82 | `909e96cb32d92ce728a01bc99850cbba26196d74115c17ebeb019275412588f2` |
| `tokenizer_config` | `tokenizer_config.json` | 1,536 | `69033fe64b478a07aa521133752d2772a9dc7b823bc2a7bb5b8944def1c9c5fd` |
| `tokenizer_json` | `tokenizer.json` | 711,661 | `da0e79933b9ed51798a3ae27893d3c5fa4a201126cef75586296df9b4d2c62a0` |
| `tokenizer_special_tokens` | `special_tokens_map.json` | 228 | `cb63d0cbbf45160dc9cd786a257759593b798ae0c72957011016dbc3972df4e4` |
| `tokenizer_vocab` | `vocab.txt` | 231,508 | `07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3` |

Exact lengths are the byte ceilings. The profile rejects missing, additional,
symlinked, nonregular, or length-mismatched files.

## Parse and allocation order

For every receiver-prepared artifact set, the provider performs this order:

1. verify the prepared set identity and the complete closed predicate;
2. `stat` every expected relative path without following symlinks; require a
   regular file and its exact length;
3. stream SHA-256 over each file and compare the table before parsing it;
4. decode the JSON assets as UTF-8 without BOM, reject duplicate object keys,
   and enforce their exact fixed length before bounded parse;
5. read the eight-byte little-endian safetensors header length; reject a value
   over 16,384 bytes, a truncated header, or an oversized JSON header before
   decoding it;
6. validate the bounded safetensors header before data access: exactly 103
   tensors, no duplicate names, only `F16` and `F32`, nonnegative monotonic
   nonoverlapping offsets, exact byte spans, and final offset 45,446,400;
7. validate the BERT, pooling, Sentence Transformer, and tokenizer semantics
   below; then create MLX arrays; and
8. instantiate the fixed BERT encoder and evaluate inputs.

The tensor predicate is fixed: embeddings consist of word
`30522x384`, position `512x384`, type `2x384` F16 tables and two F32 LayerNorm
vectors; each of six layers has F16 Q/K/V and attention-output `384x384`
matrices and biases, F16 intermediate `1536x384` and output `384x1536`
matrices and biases, and two F32 LayerNorm vectors; pooler weight is F16
`384x384` with an F16 bias. No parser, tokenizer, safetensors library, MLX
import, or allocation occurs before its preceding gate.

## Encoder and tokenizer semantics

`config.json` must describe `BertModel`: hidden size 384, 6 layers, 12 heads,
intermediate size 1,536, vocabulary size 30,522, absolute position embeddings,
position maximum 512, type vocabulary 2, GELU activation, epsilon `1e-12`,
and pad ID 0. `modules.json` must contain only the Transformer root followed by
`1_Pooling`; pooling must enable mean tokens only with dimension 384. The
sentence-transformer configuration must have `max_seq_length: 512`.

The tokenizer is a WordPiece tokenizer with 30,522 vocabulary entries,
`[UNK]` ID 100, `[CLS]` ID 101, `[SEP]` ID 102, `[PAD]` ID 0, `[MASK]` ID 103,
and `##` continuation prefix. It accepts one sequence only: the postprocessor
inserts CLS then at most 510 WordPiece tokens then SEP, all with type ID zero.
Pairs are rejected. It uses BERT clean-text and Chinese-character handling,
Unicode NFD accent removal, lowercasing, BERT whitespace/punctuation splitting,
and WordPiece's 100-character word limit. A word that cannot be segmented
becomes `[UNK]`. Input truncation therefore counts the inserted CLS and SEP in
the 512-token maximum. The provider does not use the source tokenizer's
embedded 128-token truncation or padding setting.

Pooling is the attention-mask-weighted mean of final hidden states. The fixed
normalization policy is `none`.

## MLX distribution admission

The existing `mlx` extra remains generation-only and continues to select
`mlx-lm`. MLE2 shall add a separate Darwin-only `mlx-embedding` extra that
pins `mlx==0.32.2` and does not install or import `mlx-lm`, Transformers, or a
tokenizer runtime. The normal Poetry lock supplies the wheel hashes. At
execution, the adapter requires macOS 14 or newer, arm64, a compatible Python
ABI wheel, and `mlx.__version__ == "0.32.2"`; it rejects all other platforms
and versions before material resolution. Non-Darwin package installation and
ordinary DAR import must never resolve MLX.

## Source and licensing record

The Hugging Face API listing at the pinned revision established the source
revision, filenames, lengths, and the safetensors LFS SHA-256 above. The pinned
model card and API metadata did not provide a machine-readable license. DAR
does not bundle the materials; the receiver-private material resolver fetches
the original locked files only after the existing host policy admits it. A
separate license decision is required before this profile may be offered as a
portable workflow material option.
