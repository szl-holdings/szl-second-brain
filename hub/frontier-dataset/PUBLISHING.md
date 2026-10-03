# Frontier review-handle dataset publication

The source of truth is the signed, protected main branch of
`szl-holdings/szl-second-brain`. This directory owns the Hub card template;
`scripts/publish_frontier_dataset.py` owns the exact, one-target publication.

After the publisher source is merged and the main revision is verified:

1. Check out that exact GitHub main revision in a clean worktree.
2. Run `python scripts/publish_frontier_dataset.py --receipt /outside/source/plan.json`.
3. Review the fixed target, source SHA, candidate count, authority labels, and
   source/published hashes in the plan. The plan does not mutate Hugging Face.
4. Run `python scripts/publish_frontier_dataset.py --apply --receipt /outside/source/apply.json`
   using the existing SZLHOLDINGS admin session.
5. Retain the receipt and immutable Hub revision. The script compares every
   published file byte at that revision before reporting success.

The destination is only
`SZLHOLDINGS/szl-second-brain-frontier-candidates` (dataset). Its viewer file
contains handles, not candidate excerpts or paper full text. The exact reviewed
`frontier-state.v1.json` is copied from GitHub; `publication.json` binds its
source and projection hashes. If the destination already exists with different
or incomplete bytes, the script stops without overwriting it. A later snapshot
requires an explicit, separately reviewed update mechanism and one writer.

This publication does not create a Space, run inference, train, promote,
hydrate content, or update the separate 575-chunk Alloy dataset. The source
package's Apache-2.0 licence does not resolve rights for every referenced work;
the Hub card explicitly retains mixed-source review terms.
