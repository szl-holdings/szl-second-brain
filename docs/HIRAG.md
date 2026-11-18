# HIRAG — Hierarchical Invariant-Retrieval Admission Graph

**Status: source-level core and optional hybrid wiring IMPLEMENTED; independently verified live deployment and signed issuer trust NOT ESTABLISHED.** The existing `second_brain/hirag.py`, `second_brain/admission.py` and `second_brain/hybrid.py` provide a tested local gate and optional corpus binding; the default hybrid pipeline reports `NOT_APPLIED` unless configured. A separate source-only, offline ablation in `szl-retrieval-bench` measures retrieval tradeoffs and does not grant production or training authority.

## The field's problem, restated

The [GraphRAG-Bench study (ICLR 2026)](https://github.com/GraphRAG-Bench/GraphRAG-Benchmark)
and [WildGraphBench (ACL 2026)](https://github.com/BstWPY/WildGraphBench)
show mixed outcomes: graph retrieval can help on multi-document reasoning
but can also lose to simpler retrieval. Results depend on corpus, task,
budget and evaluation; no borrowed performance percentages apply to SZL.

RAPTOR (hierarchical summaries), GraphRAG (communities), HippoRAG/2
(Personalized PageRank), and LightRAG (dual-level graphs) offer different
retrieval strategies. Their published retrieval descriptions do not prove
SZL-specific signing, licensing or time-validity admission. We do **not**
claim these systems universally lack filtering or governance.

## The SZL restatement

Context noise can arise from **ranking, retrieval, or admission**. Even a fully
authentic, licensed, fresh source may be irrelevant to the query. Conversely,
a relevant but unverified source may have to be withheld, harming recall.
Provenance is evidence of lineage, **not** a correctness or relevance oracle.
Any future admission gate must report these tradeoffs rather than hide them.

## HIRAG: three layers, unified

**HIRAG = Hierarchical Invariant-Retrieval Admission Graph.** It composes the two
paradigms the estate has been asked to unify (RAG and DAG) under the governance math:

1. **H — Hierarchical retrieval** (the RAPTOR/GraphRAG layer): the corpus is indexed at
   multiple abstraction levels (chunk → summary → community). Retrieval traverses levels
   coarse-to-fine. *This layer is commodity: use the field's best components.*

2. **IRAG — Invariant Retrieval over a provenance DAG** (the estate's layer):
   the existing core represents content nodes with a declared digest, source
   revision, license and ingestion timestamp, linked by `derived_from` edges.
   A future signed evidence graph additionally requires issuer-verified receipts
   and valid derivation authority. Today these paths can be checked for internal
   lineage consistency, **not** independently authenticated as factual evidence.
   This is the proposed DAG half of the retrieval/evidence unification.

3. **Implemented local admission core — deterministic zero-veto and advisory Λ**:
   `second_brain/hirag.py` computes the five-axis weighted geometric mean
   `Λ(x,w) = exp(Σ w_i log(x_i))`, with `Λ=0` if any `x_i=0`,
   strictly positive weights summing to one, a configured threshold, and
   a separate `ABSTAIN` outcome for numerical ties. The optional
   `second_brain/admission.py` binds corpus bytes/generation to declared
   license and ingestion metadata. Missing trust anchors fail closed;
   `metadata_presence_trust_anchor` is explicitly weak and does not
   authenticate an issuer. Rank-derived relevance `1/rank` is **not**
   calibrated answer quality. The gate's arithmetic is **advisory**,
   not a cryptographic signature verifier, proof of unconditional Λ
   uniqueness, or authorization to act. Current source-level axes:

   | Axis | Measure |
   |---|---|
   | `source_receipt_valid` | local content/corpus-generation binding through a configured trust anchor; no independent issuer signature |
   | `license_admissible` | allowlisted, owner-declared license string; legal rights have not been independently adjudicated |
   | `freshness` | decayed score from a supplied ingestion timestamp and bounded window; stale zero veto |
   | `relevance` | rank-derived `1/rank` surrogate in the optional corpus adapter; not calibrated relevance |
   | `derivation_integrity` | transitive ancestor checks through the same trust anchor; not independent signature verification |

   **Offline hypothesis:** define four declared binary veto axes
   `A(d) = ∏_{a∈{integrity, license, freshness, derivation}} 1[state_a(d)=PASS]`.
   Filter the original ranking without changing its order or the relevance
   denominator. This is a *fixture ablation*, not a production Λ score.
   A provenance veto prevents unverified input admission only when the
   verification actually exists; it does **not** eliminate all irrelevant
   context and it may remove truly relevant evidence.

## What is claimed and what is not

**Claimed:** existing HIRAG source and tests implement optional admission,
transitive provenance/declared-license refusal, a bounded freshness score,
and a strict arithmetic gate. The default hybrid route does **not** apply
it automatically, and local content hashes do not authenticate an issuer.
[`szl-retrieval-bench` PR #30](https://github.com/szl-holdings/szl-retrieval-bench/pull/30)
merged a separate stdlib-only *paired offline ablation*: its caller-declared
flags are `CALLER_DECLARED_UNVERIFIED`, `execution_authority=NONE`, and
do not enable the Second Brain runtime. The unconditional-uniqueness form
of Conjecture 1 is not a theorem.

**NOT claimed:**
- No claim that HIRAG improves recall or answer quality. The new synthetic
  ablation includes a **negative** case: withholding a relevant license-UNKNOWN
  document reduces Recall@2 from 1.0 to 0.5. This is not a real-world benchmark.
  Publicly claim an improvement only after rights-cleared, frozen evaluation
  against flat and graph baselines with the same queries, labels and cutoff.
- No claim that Λ is a theorem. The gate is advisory governance, exactly as in the
  acoustic-validation governed layer.

## The Ouroboros integration

HIRAG has an existing **source-level** DAG/gate and an optional
`CorpusAdmission` adapter into `HybridSecondBrain`. The default retrieval
mode remains `NOT_APPLIED` and the current file/hash chain is not
independently issuer-authenticated. A separate future **operational**
transaction would ingest (source record) → validate indexed lineage
→ retrieve → verify signed source and rights/freshness → admit/refuse
→ generate a proposal → review → remember with a separately authorized
signed receipt. No claim is made that the full pipeline is deployed or
that every stage currently emits a Khipu signature.

## Leaders studied (and what we take from each)

| Leader | Public research technique | Additional requirement for SZL |
|---|---|---|
| [RAPTOR](https://arxiv.org/abs/2401.18059) | hierarchical summary tree | bind each candidate summary to independently verified source units |
| [GraphRAG](https://arxiv.org/abs/2404.16130) | community-level abstraction | evaluate member attribution and source provenance separately |
| [HippoRAG/2](https://github.com/OSU-NLP-Group/HippoRAG) | PageRank over entity graphs | do not interpret rank as a rights check or calibrated trust |
| [LightRAG](https://aclanthology.org/2025.findings-emnlp.568/) | low/high-level incremental retrieval | qualify changed sources before admitting them to generation |
| [GraphRAG-Bench (ICLR 2026)](https://github.com/GraphRAG-Bench/GraphRAG-Benchmark) | task-specific baseline comparisons | publish fair flat/graph/admission ablations, including negative results |

## Evaluation plan (pre-declared, honest)

1. **Benchmarks are distinct:** GraphRAG-Bench evaluates Novel and Medical
   task families. HotpotQA, 2WikiMultiHopQA and MuSiQue are separate multi-hop
   datasets, not the named GraphRAG-Bench suites. Obtain usage rights and
   freeze the intended question sets before running either benchmark family.
2. **Conditions:** keep a common retrieval ranking and judgments for the
   first offline admission ablation, then compare flat BM25/RRF, graph
   retrieval and graph-plus-admission as separate full-system arms.
3. **Metrics:** Recall@k, P@k, nDCG@k, answer accuracy on independently
   labeled questions, refusal of relevant candidates, admission fraction,
   context relevance, p95 latency and receipt/verification overhead.
4. **No label leakage:** the gate never selects based on held-out relevance
   judgments. Report both positive and negative per-query deltas with
   unchanged ground-truth denominators; do not tune an acceptance threshold
   on the held-out test set or assert conformal risk guarantees.
5. **Publication:** retain a versioned dataset/rights statement, exact
   source and provider revisions, evaluation code and failure cases;
   include independent signed receipts only when those signatures verify.

## Implementation home

Source implementation is in [`second_brain/hirag.py`](../second_brain/hirag.py),
[`second_brain/admission.py`](../second_brain/admission.py), and
[`second_brain/hybrid.py`](../second_brain/hybrid.py), with explicit
offline tests in [`tests/test_hirag.py`](../tests/test_hirag.py) and
[`tests/test_admission_wiring.py`](../tests/test_admission_wiring.py).
`CorpusAdmission` requires exact corpus generation, recomputed row hashes,
owner-declared rights and ingestion timestamps. Its trust anchor is content
binding to the local generation, **not** a signature or independent issuer check.
The adapter is optional, not a qualified deployed service.

The separate source-only comparator is merged into
[`szl-retrieval-bench` at PR #30](https://github.com/szl-holdings/szl-retrieval-bench/pull/30);
its [exact implementation and limitations](https://github.com/szl-holdings/szl-retrieval-bench/blob/main/docs/evidence-admission-ablation.md)
are a reproducible *evaluation* tool, not a verifier, policy decision,
training authorization or deployed HIRAG. A real rollout must independently
prove signing, rights and freshness, service owner, release admission,
and source-to-provider parity.
