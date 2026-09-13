# MLE7 Material Approval

- Model closure: `intfloat/multilingual-e5-small` at revision
  `614241f622f53c4eeff9890bdc4f31cfecc418b3`.
- License decision: the upstream revision's model card declares `MIT`; local,
  non-redistributable conformance use is approved.
- Execution ABI: `bert-encoder-mlx-v4@5`.
- Material handling: the source `model.safetensors` remains a locked F32 input;
  the receiver-only `mlx.embedding.weights.prepare.v1` operation produces the
  locked mixed-precision `weights` role. The package executes no provenance
  metadata as tokenizer or model code.
- Limits: sixteen items, 512 tokens each, 512 MiB declared material/execution
  ceiling, and 16 MiB tokenizer/header ceilings.
- Boundaries: this approval authorizes package admission and local synthetic
  conformance preparation only. A Darwin/Metal competency run remains a
  separate explicit authorization gate.
