---
title: SZL Second Brain
emoji: 🧠
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Governed hybrid retrieval with controller-only hydration.
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

The public projection currently contains 575 in-repository chunks. The private
9,464-node graph is not published, is not queried by this package, and is never
admitted to gradients. The index is data, not model weights. Lambda uniqueness
remains **Conjecture 1**.

## Retrieval modes

Version 1.1 adds `HybridSecondBrain`, an engine-neutral retrieval coordinator:

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

`AuthorizedHydrator` is a library-only controller component. It requires:

- a non-empty principal ID and tenant ID;
- an immutable policy revision;
- an explicit per-node authorization callback;
- matching node identity, source, and SHA-256;
- an untampered public corpus row.

Any denial, provider error, duplicate, unknown handle, source mismatch, or digest
mismatch fails the whole hydration request closed. Hydrated text is never exposed
by the public FastAPI application.

```python
from second_brain import AuthorizedHydrator, HybridSecondBrain

retriever = HybridSecondBrain(dense_provider=my_dense_provider,
                              reranker=my_reranker)
context = retriever.context("locked formula authority", k=6)

hydrator = AuthorizedHydrator(my_authorizer)
hydrated = hydrator.hydrate(
    context["handles"],
    principal_id="principal-123",
    tenant_id="tenant-abc",
    policy_revision="<full immutable revision>",
)
```

## Public surfaces

| Surface | Contract |
|---|---|
| `GET /health` | Base index state |
| `GET /api/v1/index` | Public chunk counts by source |
| `GET /api/v1/retrieve?q=` | Legacy lexical handles-only retrieval |
| `GET /api/v1/navigator?q=` | Legacy navigator context |
| `GET /api/v1/hybrid?q=` | Governed retrieval with an explicit ranking receipt |
| `POST /api/v1/hybrid` | JSON alias for governed retrieval |
| `GET /api/v1/retrieval-capabilities` | Truthful runtime capability declaration |

GitHub is the source of truth; the Hugging Face Space is a deployed public
surface. Apache-2.0. Doctrine v11.
