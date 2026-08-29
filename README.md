---
title: SZL Second Brain
emoji: 🧠
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Handles-only retrieval hologram. Conjecture 1.
tags:
  - retrieval
  - holographic
  - governance
  - fail-closed
  - szl-holdings
---

# SZL Second Brain

**Compound system:** retrieval index (this repo) + navigator (Ayllu Maskaq / Khipu).

Public-projection retrieval hologram. Query → handles → plan JSON.
SOFTWARE navigator over **575** in-repo chunks. Handles only — content stays
in the controller.

- GitHub: [szl-holdings/szl-second-brain](https://github.com/szl-holdings/szl-second-brain)
- Space: [SZLHOLDINGS/second-brain](https://huggingface.co/spaces/SZLHOLDINGS/second-brain)

Λ uniqueness is **Conjecture 1** and is never a theorem.
The private 9464-node graph is **not published** and is **not admitted to
gradients**. Index is DATA, never weights. A BM25-like score ranks lexical
overlap; it is **never correctness**. This API never fabricates **LIVE** retrieval.

| Surface | What it is |
|---|---|
| `GET /health` | index stats, SOFTWARE |
| `GET /api/v1/index` | chunk counts by source |
| `GET /api/v1/retrieve?q=` | handles only — no node text |
| `GET /retrieve?q=` | alias |
| `GET /api/v1/navigator?q=` | Maskaq/Khipu candidate handles |

Ayllu consumes this index via PYTHONPATH / `AYLLU_SECOND_BRAIN_ROOT` /
the vendored public projection. Maskaq asks **ABSTAIN** when no handle
supports the query.

Apache-2.0. Doctrine v11.
