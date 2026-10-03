---
license: other
license_name: mixed-source-review-only
language:
  - en
pretty_name: SZL Second Brain — Frontier Review Handles
size_categories:
  - n<1K
task_categories:
  - other
tags:
  - retrieval
  - provenance
  - review-required
  - szl-holdings
configs:
  - config_name: default
    data_files: frontier-handles.public.jsonl
---

# SZL Second Brain · Frontier review handles

**137 attributed candidates · 10 source contracts · review required.** This is a public index of handles, titles, digests, and source references. It is a data publication, not model weights or an inference service. The separate [575-chunk Alloy in-repo corpus](https://huggingface.co/datasets/SZLHOLDINGS/szl-second-brain-inrepo) is a different dataset.

| What is present | What it means |
|---|---|
| 131 reviewed Git-sourced candidates | Fixed public source contracts, including two operator-authored science forum summaries. |
| 6 research metadata candidates | Bounded public Crossref and arXiv metadata captures; paper full text was not downloaded. |
| `frontier-handles.public.jsonl` | Public citation handles with exact source revisions and content digests. Raw candidate excerpts are omitted. |
| `frontier-state.v1.json` | The exact reviewed state bytes from GitHub, retaining source counts and review status. |
| `publication.json` | A source commit and SHA-256 binding for every source and published file. |

The [canonical Python source](https://github.com/szl-holdings/szl-second-brain/tree/__SOURCE_SHA__) generated this snapshot. The source candidate JSONL is SHA-256 `__CANDIDATE_SHA256__`; the published handles are SHA-256 `__HANDLE_SHA256__`. The exact state file is SHA-256 `__STATE_SHA256__`, its candidate set digest is `__CANDIDATE_SET_SHA256__`, and the reviewed research metadata snapshot is SHA-256 `__RESEARCH_SHA256__`. These hashes establish byte identity, not independent accuracy or source authenticity.

## Use and limits

Search or inspect these handles as **DISCOVERED_REVIEW_REQUIRED** candidates. Follow each handle's repository, path, revision, and digest to assess its source. The public Second Brain API returns handles; authorized content hydration remains a separate controller decision. This dataset contains no private graph rows, raw research paper text, credentials, training set, weights, or tool authority.

Training authority: **NONE**. Promotion authority: **NONE**. Execution authority: **NONE**. No measured retrieval quality, model improvement, AGI, or theorem follows from this index. Λ-uniqueness remains Conjecture 1.

## Rights and attribution

The rows aggregate references to several public repositories and public research metadata services. Rights vary by source. No blanket open-data licence or paper full-text licence is asserted by this dataset card; follow each handle to the original work and its terms. The source package's Apache-2.0 code licence does not automatically grant rights to third-party source material.

## Reproduce the publication

From the verified GitHub main revision shown above, run `python scripts/publish_frontier_dataset.py --receipt /path/to/new-plan.json` to validate the source and preview the fixed publication. The explicit `--apply` form writes only this dataset and compares every published byte at the immutable Hub revision. No API key is needed for reading this public dataset; publishing uses an existing authorized organization session.
