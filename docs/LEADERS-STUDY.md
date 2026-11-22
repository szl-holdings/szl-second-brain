# Domain Leader Study — szl-second-brain (public retrieval hologram)

OUROBOROS phase-3, cohort-02 tranche-2, Kimi ruling W26-C2T2-KIMI-20261123-ASK (GO, 7 bindings). PROPOSE-ONLY, DRAFT. Documentation only, no implementation in this PR.

## Current state (repo inspection 2026-11-23)
Python repo; description: public second-brain retrieval hologram; handles only; SOFTWARE navigator over 575 chunks. Topics: governed-ai, hologram, huggingface, knowledge-base, python, retrieval. Companion HF Space measured RUNNING in the spaces census.

## Domain leaders studied
| Leader | What they have | Key sources |
| --- | --- | --- |
| BEIR (Thakur et al.) | The reference heterogeneous benchmark for zero-shot retrieval evaluation across 18 tasks: nDCG@10 by default, per-corpus results — the canonical way to say a retrieval system is good without tuning on the test set | arxiv.org/abs/2104.08663 (accessed 2026-11-23) |
| rank_bm25 | The standard Python sparse-retrieval baseline (BM25 family, pure python): what any fancier retriever must first beat to justify itself | github.com/dorianbrown/rank_bm25 (accessed 2026-11-23) |

## What the leaders do better
- BEIR's doctrine: evaluate zero-shot with standard metrics across diverse corpora so retrieval quality is not self-referential; the estate analog is our receipts doctrine applied to search quality.
- rank_bm25 defines the floor: leaders publish the cheap baseline alongside the fancy system, so improvements are measured against something reproducible.

## Gaps
- Description-measured 575-chunk navigator exists, but no documented retrieval-quality receipt (metric, query set, baseline comparison) was found in card scope; a retrieval hologram without a measured floor cannot honestly claim findability.

## Ranked #1 absorb proposal (NOT implemented in this PR)
Adopt a BEIR-style micro-eval for the 575-chunk corpus: fixed public query set (derived from published handles), nDCG@10 + recall@k vs a rank_bm25 baseline, receipt published per run. Expected benefit: retrieval quality becomes measured and trendable across estate iterations; honest-findability claims get evidence. Cost/risk: low-medium; eval harness documented for future implementation PR, corpus is small (575 chunks) so runs are cheap. Validation: two eval runs, identical corpus, delta explained. Rollback: harness removal only.

## Sources
- BEIR paper: https://arxiv.org/abs/2104.08663 (accessed 2026-11-23)
- rank_bm25: https://github.com/dorianbrown/rank_bm25 (accessed 2026-11-23)
