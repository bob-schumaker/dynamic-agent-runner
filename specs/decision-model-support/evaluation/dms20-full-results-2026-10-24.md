# DMS-20 full results (2026-10-24)

All separately approved DMS-20 baseline, candidate, and optimization rows are
listed below. The quality gate is canonical macro accuracy ≥ 0.75 and every
category accuracy ≥ 0.40. “Gate” reflects both conditions, not speed.
Per-decision timing is mean latency in milliseconds.

| Row | Canonical macro accuracy | Mean ms / decision | Failed outputs | Quality gate |
|---|---:|---:|---:|:---:|
| Julia-1 CPU | 0.52308 | 19.825 | 0 | No |
| Kev-4B CPU | 0.80039 | 7,867.530 | 0 | Yes |
| Lev CPU | 0.78723 | 9,330.000 | 0 | Yes |
| Strands Decider 2B CPU | 0.73712 | 627.186 | 13 | No |
| Tev1-0.8B MPS | 0.62646 | 354.033 | 0 | No |
| Tev1-4B MPS | 0.78189 | 944.499 | 0 | Yes |
| Bespoke Nimble-9B MPS | 0.79401 | 1,863.194 | 0 | Yes |
| Qwen3.5-0.8B-decision MLX 8-bit | 0.52459 | 367.922 | 0 | No |
| D1A E2B MLX 8-bit | 0.59734 | 75.714 | 18 | No |
| Kev-4B MPS BF16 / SDPA | 0.79737 | 685.509 | 0 | Yes |
| Lev MPS BF16 | 0.78600 | 1,721.729 | 0 | Yes |
| Strands Decider 2B MPS BF16 | 0.74018 | 240.927 | 16 | No |
| Tev1-0.8B MPS batch 4 | 0.62769 | 302.462 | 0 | No |
| Tev1-4B MPS batch 4 | 0.78095 | 1,053.200 | 0 | Yes |
| Nimble-9B MPS batch 4 | 0.78805 | 1,949.674 | 0 | Yes |
| Nimble-9B MPS linear attention | 0.00000 | 1,448.927 | 1,368 | No |
| Qwen3.5-0.8B-decision MLX 4-bit | 0.52829 | 247.915 | 0 | No |
| D1A E2B MLX 4-bit | 0.59586 | 73.816 | 13 | No |
| Von 1.2.0 CPU | 0.69263 | 117.432* | 0 | No |

* Von reused the exact-input DMS-14 predictions because normalized input and
  label digests match; timing is from the historical DMS-14 run on an earlier
  host, so it is not a current-host timing measurement.

Nimble linear attention produced non-finite logits and 1,368 invalid outputs.
Strands MPS BF16 produced 16 failed outputs; D1A 8-bit produced 18 failures,
and D1A 4-bit produced 13. The D1A 4-bit row is only 1.026× faster than the
8-bit baseline and its canonical macro accuracy is 0.59586. Qwen 4-bit is
1.484× faster than Qwen 8-bit but remains below the quality threshold.

The proposal JSON preserves the pilot-time proposal snapshot referenced by the
Kev receipt; completed variant outcomes are listed here.

Evidence: original DMS-20 run under `dms20-run-2026-10-22/`; candidate follow-up
report `dms20-followup-evaluation-2026-10-23.json`; optimization result addenda
and per-row run receipts in this directory; Von evidence in
`dms20-von-cpu-run-2026-10-24/`. The original matrices and baseline results
remain unchanged.
