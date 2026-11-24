# HIRAG — Hierarchical Invariant-Retrieval Admission Graph

**Status: source-level core, optional hybrid wiring and an explicit served opt-in (`SECOND_BRAIN_HIRAG_ADMISSION=1`, default off) IMPLEMENTED; independently verified live deployment and signed issuer trust NOT ESTABLISHED.** The existing `second_brain/hirag.py`, `second_brain/admission.py` and `second_brain/hybrid.py` provide a tested local gate and optional corpus binding; `second_brain/admission_runtime.py` wires it into the served routes only when the operator opts in. By default the hybrid pipeline and the served routes report admission `NOT_APPLIED` for every non-empty query. The opt-in's ingestion timestamp is an unratified substitute that requires an owner decision, and with the committed metadata opting in refuses every node (see [Served runtime opt-in](#served-runtime-opt-in)). A separate source-only, offline ablation in `szl-retrieval-bench` measures retrieval tradeoffs and does not grant production or training authority.

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

1. **H — Hierarchical retrieval** (the RAPTOR/GraphRAG layer), **ROADMAP in this
   repository**: the design indexes the corpus at multiple abstraction levels
   (chunk → summary → community) and traverses them coarse-to-fine. Nothing here
   builds or traverses that hierarchy today: the served index is a flat lexical
   index, and every corpus admission node is level 0 with no `derived_from` edge.
   *This layer is commodity: use the field's best components.*

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
it automatically; the served routes apply it only when the operator sets
`SECOND_BRAIN_HIRAG_ADMISSION=1`. Local content hashes do not authenticate an issuer.
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
`CorpusAdmission` adapter into `HybridSecondBrain`. By default the retrieval
mode is `BM25_ONLY` and the ranking receipt's `admission` field is
`NOT_APPLIED`; the current file/hash chain is not
independently issuer-authenticated. A separate future **operational**
transaction would ingest (source record) → validate indexed lineage
→ retrieve → verify signed source and rights/freshness → admit/refuse
→ generate a proposal → review → remember with a separately authorized
signed receipt. No claim is made that the full pipeline is deployed or
that every stage currently emits a Khipu signature.

## Served runtime opt-in

`second_brain/admission_runtime.py` is the only served wiring. It reads
`SECOND_BRAIN_HIRAG_ADMISSION` once per process (a change needs a restart).
**The opt-in requires an owner decision before anyone relies on it**: its
ingestion timestamp is an unratified substitute (see *Inputs*), and every
configuration block says so with `owner_ratification: REQUIRES_OWNER_DECISION`.

| Value | State | Served behaviour |
|---|---|---|
| unset, empty or `0` | `NOT_APPLIED`, reason `OPT_IN_NOT_ENABLED` | Unchanged retrieval. Hybrid, query and evidence payloads and the console page are identical to the library default. |
| exactly `1`, with a sidecar that builds | `CONFIGURED` | The gate filters the brain-corpus selection on the gated routes. |
| exactly `1`, with a missing, malformed or stale sidecar | `BLOCKED`, with the sidecar reason (below) | Gated routes refuse and `/readyz` returns 503. |
| anything else, including `1` with surrounding whitespace | `BLOCKED`, reason `OPT_IN_VALUE_INVALID` | Gated routes refuse and `/readyz` returns 503. |

`/api/v1/retrieval-capabilities` and `/readyz` always carry a top-level
`hirag_admission` block. It is reported beside the readiness `components`, not
as one of them, so the console keeps its three service cards. The opt-in never
changes `public_runtime_mode` / `runtime_mode`, which stay `BM25_ONLY`: the
lexical ranking is what runs on every route. Admission participation is
reported per route by the block and per query by `ranking_receipt.admission`
(and the receipt `mode` suffix `+HIRAG_ADMISSION`).

**Routes.** The block lists routes in every state:

- `gated_routes` (only when `CONFIGURED`): `/`, `/api/v1/query`, `/api/v1/hybrid`,
  `/api/v1/evidence-graph` and `/evidence`. The hologram calls `/api/v1/query`
  and inherits its result.
- `blocked_routes` (only when `BLOCKED`): the same five routes, which refuse.
- `ungated_routes`: `/retrieve`, `/api/v1/retrieve`, `/plan`, `/api/v1/plan`,
  `/api/v1/navigator`, `/api/v1/frontier-handles` and `/api/v1/anatomy-feed`. They
  call the index directly and keep serving lexical handles in every state,
  including `BLOCKED`. When `NOT_APPLIED`, every retrieval route is listed here.
  A test fails if any route that accepts a query is missing from these lists.
- `gate_scope: BRAIN_CORPUS_HANDLES_ONLY`. Inside the gated routes only the
  brain-corpus handles are gated. The research and formula review-candidate
  handles that `/`, `/api/v1/query` and the evidence graph return in the same
  response, and the evidence graph's Lutar reference handles, are not
  (`not_gated_within_gated_routes`).

**Inputs.** The gate is built only from the committed sidecar
[`data/corpus-admission-metadata.v1.json`](../data/corpus-admission-metadata.v1.json),
re-read against the same corpus file and generation the served index loaded.
The sidecar records:

- `corpus_sha256` and `row_count` of the corpus it describes.
- One `ingested_at` for the whole corpus: `1788009755` (`2026-08-29T13:22:35Z`),
  kind `REPOSITORY_ADMISSION_COMMIT_TIME`. This is the committer time of
  `ba400df`, the only commit that touched `data/brain-corpus.public.jsonl`; its
  signature is `NOT_VERIFIED`. The library contract
  (`second_brain/admission.py`) asks for a controller-measured ingestion time.
  No such observation exists for this corpus, so the opt-in substitutes the
  commit time, and that substitution is **not ratified**: the owner must decide
  whether it is acceptable. The commit time is an upper bound on when the
  projection was built, not an upstream ingestion observation. As a freshness
  input it can therefore only overstate freshness, which leans toward
  admission rather than failing closed. Each block discloses this
  (`ingested_at.substitutes_for`, `ratification`, `bound`, `freshness_bias`).
- `licenses: {}` with `ABSENT_IS_UNKNOWN`. No per-row rights are declared, and the
  repository Apache-2.0 licence is not treated as a per-row adjudication. A
  future declaration must name its own `license`, `basis` and `declared_by`. A
  declared value of `unknown` (any case) is rejected: unknown rights are
  expressed by omission, so `unknown_license_count` counts every row without
  a real declaration.

`tools/check_admission_metadata.py` (a CI selftest step with full history)
recomputes every claim in the sidecar. The cited commit must be a mainline
(first-parent) commit of `HEAD` that touched the corpus, its committer time must
equal `unix_s`, `utc` must render it, and the corpus bytes at that commit must
hash to `corpus_sha256`. A shallow clone, an absent commit or an off-mainline
commit fails. The check then reports the sidecar as `CURRENT` (it names the
working-tree corpus bytes) or `STALE`. `STALE` does not fail CI. This
repository squash-merges, so a pull request cannot cite the commit that will
land its corpus bytes: that commit does not exist until the merge, and a
branch commit is dropped from `main` by the squash. A corpus change therefore
leaves the sidecar `STALE`. While it is stale, the opt-in is `BLOCKED` with
`METADATA_GENERATION_MISMATCH`. A follow-up change regenerates the sidecar
from the mainline commit that landed the bytes. The default (opt-in off) is
unaffected either way.

The following all give `BLOCKED`: a missing or unreadable sidecar, a
generation mismatch (including a stale sidecar), unknown keys, a value of the
wrong JSON type, a `row_count` mismatch, a `utc` string that disagrees with the
epoch, a stamp below `1000000000`, a stamp in the future (which also catches
millisecond values), an unrecognised timestamp kind, any signature state other
than `NOT_VERIFIED`, a declared `unknown` licence, or any unforeseen build error
(`ADMISSION_BUILD_ERROR`, with `error_type`). While `BLOCKED`:

- `/api/v1/query` (including an empty `q`), `/api/v1/hybrid` (GET and POST) and
  `/api/v1/evidence-graph` return HTTP 422 `BLOCKED`.
- `/` with a non-empty `q` returns 422. `/` with no query returns 200 and names
  the blocked state and its reason on the page.
- `/evidence` returns 503, and `/readyz` returns 503 with `ready: false` and
  `hirag_admission.state: BLOCKED`.
- `/api/v1/retrieval-capabilities` returns 200 with the `BLOCKED` block.

Gated retrieval never falls back to an ungated answer, and never substitutes
load time, file mtime or wall-clock time for the recorded stamp.

**Policy** (reported in `hirag_admission.policy`): `tau` 0.5; equal weights 0.2
on the five axes; freshness decays linearly to 0 over a 30-day window from
`ingested_at` (a code constant; the sidecar cannot set or widen it);
admissible licences `apache-2.0`, `mit`, `cc-by-4.0` and `bsd-3-clause`,
compared case-insensitively; `GO` only when Λ is strictly above `tau`;
`ABSTAIN` when |ln Λ − ln τ| ≤ 1e-9, a tie band in log space; relevance is
`1/rank` over the post-limit selection. Refused nodes are dropped with no
backfill. Λ is Conjecture 1 and advisory here: it filters, it is not a theorem.

**Receipts when `CONFIGURED`.** `ranking_receipt.admission` is `APPLIED`, or
`NOT_RUN` for an empty query or unbuilt index. `admission_detail` adds the
following:

- `evaluated_at_unix_s`: the single clock reading the gate used for the query.
- `decision_label: COMPUTED_OVER_DECLARED_INPUTS` and `lambda_status: ADVISORY`.
- `offered_rank_order`: the offered node IDs as an ordered list. A node's
  relevance is `1/(position + 1)` in this list.
- `refusals`: a map giving each refused node's verdict, code, Λ and zero-valued axes.

`ranking_receipt.admission_runtime` carries the configuration in force,
including the policy, the `ingested_at` stamp and `metadata_sha256`. The
existing `ranking_receipt_sha256` binds all of these. Canonical hashing sorts
object keys, so the `decisions` and `refusals` maps do not bind an order.
`offered_rank_order` is a list, so the digest does bind the rank order.
Each decision can be recomputed from digest-bound inputs: the policy,
`evaluated_at_unix_s`, `offered_rank_order` and the freshness input
`admission_runtime.ingested_at.unix_s`. The per-node licence comes from the
sidecar named by `metadata_sha256`. The `source_receipt_valid` and
`derivation_integrity` axes are not recorded per node; they equal 1.0 by
construction for this flat, content-bound corpus. Because `evaluated_at_unix_s` is
recorded, two otherwise identical queries have different
`ranking_receipt_sha256` values while the opt-in is on. The receipt stays
`UNSIGNED_CONTENT_DIGEST`. When the opt-in is off, no `admission_runtime` key
is added and served receipts are unchanged.

**What opting in does today.** Every row's licence is unknown, so every node is
refused (`ZERO_VETO` on `license_admissible`), and every gated corpus query
returns `ABSTAIN_NO_GROUNDED_HANDLES`. The evidence surfaces follow: with no
grounded handles, `/api/v1/evidence-graph` and `/evidence` report
`PARTIAL_OR_UNAVAILABLE` with HTTP 503 for every query. On `/` and
`/api/v1/query` the corpus column is empty, and review-candidate handles are
still returned. The console names the configured state and the refusal count.
That is the gate reporting the absence of declared rights, not a fault.

**The freshness window for the shipped corpus has closed for good.** It ended
at `2026-09-28T13:22:35Z` (`ingested_at` + 30 days; also reported as
`ingested_at.freshness_window_ends_utc`). After that, freshness is 0 for every
row, so **declaring licences alone can never admit any node of the current
corpus**: a test declares an admissible licence for every row and still
admits nothing, with `freshness` as the only zero axis. Admission would need
one of two things, and both are owner decisions:

- New corpus bytes landed on `main`, then a follow-up regenerating the
  sidecar. The new stamp opens a fresh 30-day window. Changing the corpus
  also moves `PUBLIC_CORPUS_SHA256` and the showcase pins.
- A code change to the policy, such as `FRESHNESS_WINDOW_S` or a ratified
  re-admission stamp. Neither exists in this schema.

This, and the unratified timestamp, is why the default stays off.

**Follow-ups (ROADMAP, not done here):** an owner decision on the ingestion
timestamp substitute and on any rights declarations; a re-admission mechanism
for an unchanged corpus; per-node codes inside
`second_brain/hybrid.py` itself (that file's hash is pinned by
`examples/showcase/baseline.json`); gating the legacy routes and the
review-candidate handles; relabelling the
library-internal `truth_label: MEASURED_ADMISSION_DECISION` / `MEASURED_ADMISSION_RUN`
in `second_brain/hirag.py`, which the served receipt does not expose.

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
[`second_brain/admission.py`](../second_brain/admission.py),
[`second_brain/hybrid.py`](../second_brain/hybrid.py) and the served opt-in
[`second_brain/admission_runtime.py`](../second_brain/admission_runtime.py), with
offline tests in [`tests/test_hirag.py`](../tests/test_hirag.py),
[`tests/test_admission_wiring.py`](../tests/test_admission_wiring.py),
[`tests/test_hybrid.py`](../tests/test_hybrid.py),
[`tests/test_admission_runtime.py`](../tests/test_admission_runtime.py) and
[`tests/test_served_admission_http.py`](../tests/test_served_admission_http.py).
`CorpusAdmission` requires the exact corpus generation, recomputed row hashes
and a controller-measured ingestion timestamp for every row (the served
opt-in's commit-time substitute is unratified; see above). A missing licence is not a
construction error: it becomes `unknown` and is refused at gate time. Its trust
anchor is content binding to the local generation, **not** a signature or
independent issuer check. The adapter is optional, not a qualified deployed service.

The separate source-only comparator is merged into
[`szl-retrieval-bench` at PR #30](https://github.com/szl-holdings/szl-retrieval-bench/pull/30);
its [exact implementation and limitations](https://github.com/szl-holdings/szl-retrieval-bench/blob/main/docs/evidence-admission-ablation.md)
are a reproducible *evaluation* tool, not a verifier, policy decision,
training authorization or deployed HIRAG. A real rollout must independently
prove signing, rights and freshness, service owner, release admission,
and source-to-provider parity.
