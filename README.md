---
title: SZL Second Brain
emoji: 🧠
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Governed retrieval and review-gated continuous frontier memory.
tags:
  - retrieval
  - hybrid-search
  - governance
  - fail-closed
  - evidence
  - szl-holdings
---

# SZL Second Brain

A governed memory plane for SZL inference: **public handles and digests outside;
authorized content hydration inside the trusted controller**.

The public projection contains 575 governed chunks. The private 9,464-node graph
is not published, is not queried by this package, and is never admitted to
gradients. The index is data, not model weights. Lambda uniqueness remains
**Conjecture 1**.

Public retrieval handles now retain an admitted row's `sourceId` so a reviewer
can follow its citation. This is an additive handle field; model-facing
navigator handles still omit it and never expose text. The separate
[science-forum corpus pilot](https://github.com/szl-holdings/szl-science-forum-corpus/tree/330f519c8208eb2d6ba29492c778a0a40018195b)
emits compatible, rights-gated candidate rows. Its two operator-authored
summaries are included in the separate **review-required frontier** at an exact
source revision. It is **not admitted** to this 575-chunk retrieval corpus,
model weights, or the existing Hugging Face/Anatomy projections. The source
index is also [mirrored on Hugging Face at an exact revision](https://huggingface.co/datasets/SZLHOLDINGS/szl-science-forum-corpus/tree/76e90b85678b501d14090c2964f50c01907dfe1b);
that mirror does not grant training or promotion authority. An Anatomy source
refresh and provider readback are separate release steps.

## Installed-mode guarantee

Version 1.5 packages the public corpus, schemas, and the review-gated frontier
candidate index into the wheel. Installing `szl-second-brain` in a clean
environment can build the 575-chunk index, run governed hybrid retrieval, inspect
the exact frontier state, search review candidates by handles, and perform
controller-only authorized hydration without a source checkout.

The wheel contains only public material. It contains no private graph rows,
credentials, model weights, signing keys, or execution authority. CI builds the
wheel, installs it into an isolated environment, changes outside the repository,
and proves corpus discovery, frontier discovery, retrieval, digest parity,
Living Anatomy feed generation, and authorized hydration.

An operator may still provide a different governed projection through
`SECOND_BRAIN_CORPUS` or `AYLLU_BRAIN_CORPUS`. Explicit corpus paths remain
controller decisions and must pass the same per-row digest checks.

## Continuous frontier memory

The hourly `Continuous frontier memory` workflow is a bounded discovery loop,
not autonomous retraining. It reads only eight fixed public source contracts:

- the exact `szl-formulas` formula/quant atlas;
- the canonical `szl-ouroboros` bounded-loop kernel README;
- the canonical `szl-kernels` governed suite and MiniEmbed truth card;
- the Living Anatomy README;
- the A11oy public-estate manifest;
- the Forge production-controller contract;
- the Nemo witness README;
- the reviewed, operator-authored science-forum insight index.

Each source is resolved to the latest exact commit that changed its admitted
path, fetched from immutable raw GitHub, scanned for secret-like material, and
converted into content-addressed candidates. The committed state records the
exact candidate count and digest, including 30 attributed formulas, 21
executable formulas, nine quant domains, the active kernel/model truth cards,
the A11oy public topology, Forge controller contracts, and source-document
sections.
The forum parser accepts exactly the two reviewed operator records for topics
#396 and #426 in either order. It rejects unknown or duplicate topics, unapproved
rights, duplicate JSON keys, extra raw-post fields, and a changed source count.
It contributes two `forum-insight` candidates while preserving the other 129
candidate rows byte-for-byte and keeping all candidates review-required.
This convenience sample is not a forum-wide scrape. Topic #396 comes from the
operator's text supplied in the corpus task; its forum page was not independently
accessible. Source links and original summaries grant no model-training authority.

A changed candidate set creates one content-addressed review branch and attempts
to open its pull request. When organization policy blocks Actions from opening
pull requests, the receipt reports `BRANCH_READY_EXTERNAL_PR_REQUIRED` and an
authorized founder must open that exact branch without rewriting it. The workflow
cannot force-push, merge, train, publish weights, reveal candidate content through
the public API, load the private graph, or mutate a provider. Candidate state is
always `DISCOVERED_REVIEW_REQUIRED` until a separate reviewed process acts.

This is the operational meaning of “the Brain keeps learning” here:

```text
fixed public sources
       ↓ exact path revisions + SHA-256
bounded candidate extraction
       ↓
handles-only review index
       ↓
content-addressed review PR
       ↓
human-governed acceptance or rejection
```

It is continuous evidence acquisition, not silent model self-modification.

## Public research metadata

The reviewed research snapshot adds six real metadata nodes to the existing 131
frontier candidates: Shannon on communication, Wigner on mathematics in natural
science, LeCun/Bengio/Hinton on deep learning, LeCun and colleagues on document
recognition, Angelopoulos/Bates on conformal uncertainty, and Cranmer on symbolic
regression for science. The eight reviewed Git source contracts remain exact;
the two metadata providers bring the current source count to ten.

`scripts/collect_public_research.py` accepts explicit DOI and arXiv identifiers.
It uses the public HTTPS APIs with no credentials, one connection, no redirects,
and limits of twelve requests, 256 KiB per response, 32 authors, and 96 retained
record versions. It records titles, authors, publication dates, categories,
source links and declared metadata licences. It does not download paper text,
follow supplied links, train a model, or grant execution authority. A missing
full-text licence remains `NOT_INFERRED`.

```sh
python scripts/collect_public_research.py \
  --doi 10.1002/cpa.3160130102 --report reports/research-collection.json
python scripts/refresh_frontier_memory.py
```

The collector writes `data/public-research-metadata.v1.json` atomically only
after all requested records pass. Its changes still require normal Git review;
the hourly frontier refresh consumes the reviewed snapshot without making
research API calls. Identical metadata preserves the first capture and creates
no extra node. Changed projected bytes retain the earlier capture and create a
new content-addressed version. An arXiv run also requires `--exclusive-arxiv`
after coordinating the single collector across all controlled machines; calls
are at least three seconds apart, including failures.

Research handles declare `revisionKind: metadata-capture-sha256` and include a
source identity, canonical link, observation time, and licence status. Git
handles retain exact Git revisions. Captured-byte integrity is separate from
independent source attestation. Public handles never contain paper abstracts or
captured raw bytes. Authorized hydration requires the complete offered handle,
rejects duplicate or altered source bindings, and rechecks the 180-day metadata
age even when the index has been loaded for a long time. Expired captures fail
closed; they do not grant a freshness or correctness claim.

The public research nodes use the existing lexical relevance index. There is no
new embedding model or dense-vector qualification in this release. Small local
retrieval fixtures establish software integration; they are not a general
retrieval benchmark, scientific proof, or AGI result.

## Formula and quant authority

The frontier memory consumes `szl-holdings/szl-formulas` as the active executable
kernel and its source-attributed formula/quant atlas. The atlas preserves all 30
attributed records and nine quant domains while keeping three different concepts
strictly separate:

- per-obligation `PROOF_STATUS` on the 21 executable functions;
- source-reported status on the attributed formula corpus;
- membership in the locked-proven set of exactly eight formulas.

No status string promotes a formula. The F-number-to-executable mapping remains
`UNKNOWN_NOT_INFERRED`, and Lambda remains `CONJECTURE_1_OPEN_ADVISORY_ONLY`.
Empirical and conjectural records are evidence or review inputs, never execution
authority.

## Retrieval modes

`HybridSecondBrain` is an engine-neutral retrieval coordinator:

```text
BM25 candidates
      +
optional revision-pinned dense candidates
      ↓
reciprocal-rank fusion
      ↓
optional reranker
      ↓
source-diversity limit
      ↓
handles + source/content digests only
```

The public Space deliberately has no opaque dense provider configured, so it
reports `BM25_ONLY`. A trusted Forge deployment can inject a qualified dense
provider and reranker. If a provider fails, the response either blocks or
explicitly reports `BM25_FALLBACK_DENSE_UNAVAILABLE`; it never claims a hybrid
run that did not occur. Similarity and ranking are never represented as
correctness.

## Authorized hydration

`AuthorizedHydrator` and `AuthorizedFrontierHydrator` are library-only controller
components. They require:

- a non-empty principal ID and tenant ID;
- an immutable policy revision;
- an explicit per-node authorization callback;
- matching node identity, source, and SHA-256;
- an untampered public corpus or frontier-candidate row.

Any denial, provider error, duplicate, unknown handle, source mismatch, or digest
mismatch fails the whole hydration request closed. Hydrated text is never exposed
by the public FastAPI application.

```python
from second_brain import (
    AuthorizedFrontierHydrator,
    AuthorizedHydrator,
    HybridSecondBrain,
    frontier_search,
)

retriever = HybridSecondBrain(
    dense_provider=my_dense_provider,
    reranker=my_reranker,
)
context = retriever.context("locked formula authority", k=6)

hydrator = AuthorizedHydrator(my_authorizer)
hydrated = hydrator.hydrate(
    context["handles"],
    principal_id="principal-123",
    tenant_id="tenant-abc",
    policy_revision="<full immutable revision>",
)

review = frontier_search("formula quant anatomy ouroboros", k=12)
review_hydrator = AuthorizedFrontierHydrator(my_frontier_authorizer)
review_content = review_hydrator.hydrate(
    review["handles"],
    principal_id="reviewer-123",
    tenant_id="tenant-abc",
    policy_revision="<review policy revision>",
)
```

## Public surfaces

| Surface | Contract |
|---|---|
| `GET /health` | Base 575-chunk index state |
| `GET /api/v1/index` | Public chunk counts by source |
| `GET /api/v1/retrieve?q=` | Legacy lexical handles-only retrieval |
| `GET /api/v1/navigator?q=` | Legacy navigator context |
| `GET /api/v1/hybrid?q=` | Governed retrieval with an explicit ranking receipt |
| `POST /api/v1/hybrid` | JSON alias for governed retrieval |
| `GET /api/v1/retrieval-capabilities` | Truthful runtime capability declaration |
| `GET /api/v1/frontier-status` | Exact candidate/source/digest state, no content |
| `GET /api/v1/frontier-handles?q=` | Handles-only review-candidate search |
| `GET /api/v1/anatomy-feed` | Read-only Brain/formula/quant/Ouroboros feed for Living Anatomy |

GitHub is the source of truth; the Hugging Face Space is a deployed public
surface. Apache-2.0. Doctrine v11.
