# HIRAG — Hierarchical Invariant-Retrieval Admission Graph

**Status: SPECIFICATION v0.1 (design; no implementation claims)**

## The field's problem, restated

The 2025 systematic evaluations (RAG vs. GraphRAG, GraphRAG-Bench, LinearRAG) found that
graph-based retrieval frequently *underperforms* naive RAG: the recall gained from graph
traversal is offset by noisy, ambiguous context admitted into generation (context relevance
36.9%–54.6% for LightRAG/HippoRAG-class systems vs. 62.9% vanilla).

The field's methods — RAPTOR (hierarchical summarization trees), GraphRAG (community
hierarchies), HippoRAG/2 (hippocampal Personalized PageRank), LightRAG (dual-level graphs) —
all retrieve *more*, then rank. None of them **admit**.

## The SZL restatement

Noise in the context window is not a ranking failure; it is an **admission failure**. A
chunk that enters the generation context without provenance is an unverified claim about
the world. The doctrine's answer applies directly: model output is an untrusted proposal;
admission passes a deterministic gate.

## HIRAG: three layers, unified

**HIRAG = Hierarchical Invariant-Retrieval Admission Graph.** It composes the two
paradigms the estate has been asked to unify (RAG and DAG) under the governance math:

1. **H — Hierarchical retrieval** (the RAPTOR/GraphRAG layer): the corpus is indexed at
   multiple abstraction levels (chunk → summary → community). Retrieval traverses levels
   coarse-to-fine. *This layer is commodity: use the field's best components.*

2. **IRAG — Invariant Retrieval over a provenance DAG** (the estate's layer): every
   retrievable unit is a node in a directed acyclic **provenance graph** — each node
   carries its source receipt (content hash, source revision, license, timestamp,
   ingestion receipt ID). Edges are *derived-from* relations (a summary node derives
   from its source chunks). Retrieval paths are therefore verifiable evidence chains,
   not similarity guesses. *This is the DAG half of the unification: the retrieval
   structure is the provenance structure.*

3. **The Admission Gate — Λ-spine with zero-veto** (the SZL math): a retrieved node is
   *admitted to the generation context* only if its measured axis scores pass the
   `szl.lambda/v1` gate. Axes per node (each MEASURED, none invented):

   | Axis | Measure |
   |---|---|
   | `source_receipt_valid` | 1.0 iff the node's provenance receipt verifies against the chain |
   | `license_admissible` | 1.0 iff the source license permits the use (query-time check) |
   | `freshness` | 1.0 iff within the declared freshness window, scaled decay after |
   | `relevance` | the retriever's measured score, honestly carried (not clamped) |
   | `derivation_integrity` | 1.0 iff every derived-from edge verifies (summary nodes) |

   **Zero-veto**: a node with a failed receipt, an inadmissible license, or a broken
   derivation edge scores Λ = 0 and is **refused admission** — no matter how relevant it
   ranks. This is the direct answer to the field's noise finding: the 37–55% irrelevant
   context that GraphRAG admits is, in HIRAG, non-admissible by construction wherever its
   provenance fails.

## What is claimed and what is not

**Claimed (design-level):** the admission gate is a deterministic, receipt-backed filter
that composes with any hierarchical retriever. The zero-veto property is inherited from
`szl.lambda/v1` (advisory; Conjecture 1 machine-checked false as stated — the gate does
not depend on uniqueness).

**NOT claimed:**
- No claim that HIRAG improves recall or answer quality — that is a measurable hypothesis,
  not a design property. The evaluation protocol: run the GraphRAG-Bench suite with the
  gate on/off and publish both receipts verbatim, including any regression.
- No claim that Λ is a theorem. The gate is advisory governance, exactly as in the
  acoustic-validation governed layer.

## The Ouroboros integration

HIRAG is the Second Brain's retrieval architecture: the memory corpus (`brain-corpus`,
`frontier-candidates`) is already receipt-bearing; the frontier memory is already
review-gated. HIRAG generalizes that pattern: **retrieval = evidence, admission =
governance, generation = proposal, and every stage emits a Khipu receipt.** The loop:
ingest (receipt) → index (DAG) → retrieve (hierarchical) → admit (Λ gate) → generate
(proposal) → review (gate the output) → remember (receipt). Ouroboros closes.

## Leaders studied (and what we take from each)

| Leader | Take | Leave |
|---|---|---|
| RAPTOR (Sarthi et al., 2024) | hierarchical tree indexing | no provenance on summary nodes → our `derivation_integrity` axis |
| GraphRAG (Edge et al., 2024) | community-level abstraction | community summaries admit unverified members → gate each member |
| HippoRAG/2 (Gutiérrez et al., 2024/25) | PageRank over entity graphs | PageRank measures centrality, not admissibility → keep for retrieval, gate for admission |
| LightRAG (Guo et al., 2024) | dual-level incremental indexing | same admission gap |
| A-RAG (2026) | hierarchical retrieval *interfaces* for agents | interfaces without governance → our gate is the missing policy layer |

## Evaluation plan (pre-declared, honest)

1. Benchmark: GraphRAG-Bench multi-hop suites (HotpotQA, 2WikiMultiHopQA, MuSiQue).
2. Conditions: (a) hierarchical retrieval, ungated; (b) same retrieval + Λ admission gate.
3. Metrics: answer accuracy, **context relevance** (the field's failure metric), admission
   rate, and the receipt overhead.
4. Publication: both conditions' receipts published verbatim, including any case where
   the gate *hurts* accuracy by refusing a relevant-but-unproven node. That trade-off —
   precision of provenance vs. recall of context — is the honest open question HIRAG poses
   to the field.

## Implementation home

This specification belongs to the Second Brain (this repository): the corpus, the
review-gated frontier memory, and the receipt infrastructure already exist here. The
admission gate implementation composes `szl.lambda/v1` (szl-lambda-gate reference) with
the per-node axis measurements above. The hierarchical retriever is commodity — pluggable,
not rebuilt.
