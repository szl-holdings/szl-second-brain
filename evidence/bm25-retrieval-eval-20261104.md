# BM25 retrieval eval — MEASURED receipt (gap B1)

**Credit:** Stephen Lutar  
**Stamp:** 2026-11-04  
**Λ:** Conjecture 1 (advisory)  
**Scope:** Public 575-chunk projection · `HANDLES_ONLY` · BM25-only · no dense / GraphRAG / HiRAG claim

## Artifacts

| Path | Role |
|---|---|
| `tools/bm25_eval/frozen_queries.v1.json` | Frozen ≤30-query set (revision `bm25-eval-queries.v1`) |
| `tools/bm25_eval/run_bm25_eval.py` | Offline runner over `SecondBrainIndex` |
| `evidence/bm25-retrieval-eval-receipt.json` | Full MEASURED receipt + per-query details |

## Corpus pin

| Field | Value |
|---|---|
| Chunks loaded | **575** |
| Corpus file SHA-256 | `387337acbd8fe443637102fe7ea75387fa4c3d9d746d8ab6e2d14d6c138aad8f` |
| Manifest `projectionSha256` | `d02487523b451b390125bc3c0a20e259c44b5715528fac69cf789ca56755ea10` |
| Secret scan (manifest) | PASS |
| Private graph in index | **0** |
| Retriever/corpus git SHA | `df418d2987be479a212ae0b50a3ebc54b593d84f` (main tip under test) |

## MEASURED metrics

Frozen set: **30** queries · **21** RETRIEVE · **3** EMPTY_INDEX abstain · **6** NO_SUPPORT abstain.

| Metric | @5 | @10 |
|---|---|---|
| Micro Recall | **32/32 (1.000)** | **32/32 (1.000)** |
| Macro Recall (mean) | **1.000** | **1.000** |
| All-required | **21/21 (1.000)** | **21/21 (1.000)** |
| Gold citation hit rate | **21/21 (1.000)** | **21/21 (1.000)** |

| Contract / abstention | Value |
|---|---|
| HANDLES_ONLY handle contract | **30/30 (1.000)** — no `text` / `_toks` leaked |
| EMPTY_INDEX abstention correct (`ready=false`) | **3/3** |
| NO_SUPPORT cases | **6** |
| NO_SUPPORT `ready=true` (lexical noise) | **6** |
| NO_SUPPORT `ready=false` | **0** |

## Reading

- RETRIEVE queries are entity / cross-source / theme anchored against admitted chunk IDs. Lexical BM25 recovers all gold IDs at k=5 on this frozen set.
- EMPTY_INDEX abstention (empty string / unknown tokens) is correct.
- NO_SUPPORT questions have **no gold answering chunk**. BM25 still returns weak hits on all six — lexical rank alone does **not** implement policy abstention. Do not treat `ready=true` as supported answer.
- Score is overlap, never correctness. This receipt does **not** establish dense+RRF or hierarchy gains.

## Reproduce

```bash
python3 tools/bm25_eval/run_bm25_eval.py \
  --out evidence/bm25-retrieval-eval-receipt.json
```

*Unsigned content checksum receipt. Not an attestation. Not a Λ upgrade.*
