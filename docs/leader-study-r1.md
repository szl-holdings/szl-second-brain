# szl-second-brain domain leader study r1 (propose-only)

Date: 2026-11-24. Method: web-verified leader landscape + governing-seat synthesis (Kimi nonce T4-SZL-SECOND-BRAIN-BRIEF). This card is documentation only; it changes no code, CI, config, or existing PR status. All absorb actions are FUTURE PROPOSALS (non-authorizing); implementation and merges remain separately reviewed and gated.

## Domain: governed retrieval memory plane (BM25+dense fusion, review-gated continuous frontier memory)

## Leaders studied (web-verified 2026-11-24)

1. rank-bm25 (https://pypi.org/project/rank-bm25/) — moat: the de-facto small BM25 implementation everyone benchmarks lexical retrieval against.
2. Qdrant (https://github.com/qdrant/qdrant) — moat: production-grade open vector search with quantization and filtered hybrid retrieval.
3. Pyserini (https://github.com/castorini/pyserini) — moat: the reference hybrid BM25+dense (sparse+dense fusion) retrieval toolkit from the IR research community.

## Absorb actions (FUTURE PROPOSALS, non-authorizing)

1. (rank-bm25) Propose a receipts-first lexical baseline comparison of the current BM25 candidate path against rank-bm25 on a fixed public-only evaluation slice, reporting retrieval metrics separately from correctness and preserving BM25_ONLY / BM25_FALLBACK_DENSE_UNAVAILABLE truthfulness. Cost/limit: requires a reviewed dependency and reproducible evaluation design; no speedup or ranking-quality improvement is claimed in advance.
2. (Qdrant) Propose a design-only evaluation of Qdrant-style quantization and filtered hybrid retrieval as an optional, revision-pinned dense candidate backend, with public handles/digests remaining outside and authorized hydration remaining inside the trusted controller. Cost/limit: adds infrastructure, filter-semantics, and failure-mode review burden; the private 9464-node graph remains unpublished, unqueried here, and never admitted to gradients, and no LIVE dense availability is implied.
3. (Pyserini) Propose a documentation-and-evaluation comparison against Pyserini's sparse+dense fusion conventions to review reciprocal-rank fusion, optional reranker reporting, and reproducible retrieval receipts without representing ranking as correctness. Cost/limit: research-toolkit conventions may not transfer directly to this governed memory plane, and any experiment must remain bounded, public-only where applicable, and separately reviewed.
4. (baseline) Propose a conformance checklist that keeps frontier candidates content-addressed and DISCOVERED_REVIEW_REQUIRED, preserves the single review branch + PR attempt and BRANCH_READY_EXTERNAL_PR_REQUIRED path, and rechecks fail-closed behavior for /readyz, malformed input, invented handles, licence NOT_INFERRED, 180-day age rechecks, AuthorizedHydrator denials/mismatches, and per-call lutar sha256 integrity. Cost/limit: this is a proposed review artifact only; it does not establish new coverage, change the wheel's public-material-only boundary, or alter Lambda's Conjecture 1 OPEN advisory status.

## Do not do (per governing seat)

Do not merge, bypass the signature wall, or claim implementation beyond this card.
