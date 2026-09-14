# MLE8 Material Approval

- Model closure: `sentence-transformers/all-distilroberta-v1` at revision `842eaed40bee4d61673a81c92d5689a8fed7a09f`.
- License decision: Apache-2.0; local, non-redistributable conformance use is approved.
- Execution ABI: `roberta-encoder-mlx-v1@1`.
- Material handling: the locked F32 source safetensors closure is transformed
  only by `mlx.embedding.roberta.weights.prepare.v1`, removing the verified
  source-only position-ID and unused pooler groups. The execution descriptor
  consumes only sealed `vocab.json`, `merges.txt`, and prepared weights.
- Boundaries: package admission and local synthetic conformance preparation are
  authorized. A Darwin/Metal competency run remains separately gated.
