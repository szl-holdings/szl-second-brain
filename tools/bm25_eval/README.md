# BM25 retrieval eval (MEASURED baseline)

Offline eval of `SecondBrainIndex` lexical retrieval against the admitted
**575-chunk** public projection.

## What this is

- Frozen query set: `frozen_queries.v1.json` (≤30 cases)
- Runner: `run_bm25_eval.py` (repo checkout + stdlib; uses in-tree `second_brain`)
- Metrics: Recall@5 / Recall@10, gold citation hit rate, HANDLES_ONLY handle
  contract, EMPTY_INDEX abstention count, NO_SUPPORT ready-noise count

## What this is not

- Not dense / hybrid / GraphRAG / HiRAG
- Not a Λ theorem or correctness proof
- Lexical rank ≠ answer correctness

## Run

From the repository root:

```bash
python3 tools/bm25_eval/run_bm25_eval.py \
  --out evidence/bm25-retrieval-eval-receipt.json
```

Credit: Stephen Lutar. Λ = Conjecture 1.
