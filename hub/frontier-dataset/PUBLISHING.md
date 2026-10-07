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
5. Retain the pre-write intent, result receipt, and immutable Hub revision. The
   script compares every published file byte at that revision before reporting
   success. A failure receipt marks the provider outcome unknown; inspect the
   target before another attempt.

To update this same dataset after a new protected source merge, pass
`--expected-hub-revision` with the exact current dataset SHA to both plan and
apply. The publisher first rechecks every prior Hub byte against its signed
GitHub source ancestor, then uses that Hub SHA as the commit parent. A moved or
unowned target fails before the write.

The destination is only
`SZLHOLDINGS/szl-second-brain-frontier-candidates` (dataset). Its viewer file
contains handles, not candidate excerpts or paper full text. The exact reviewed
`frontier-state.v1.json` is copied from GitHub; `publication.json` binds its
source and projection hashes. A changed existing dataset fails unless its
current Hub revision is supplied and the previous publication is verified.

This publication does not create a Space, run inference, train, promote,
hydrate content, or update the separate 575-chunk Alloy dataset. The source
package's Apache-2.0 licence does not resolve rights for every referenced work;
the Hub card explicitly retains mixed-source review terms.


## Refresh contract and historical replay

A refresh proposal does not qualify for publication merely because its row count
matches. The publisher binds the complete SHA-256 triple of candidate JSONL,
state JSON and research-metadata JSON to the structurally reviewed counts. The
137-row prior input set remains explicit so a guarded update can reconstruct and
verify the old publication before writing. The 141-row proposal has a distinct
input triple; combining files from the two sets or making a self-consistent,
same-count edit remains blocked until a new source review changes these pins.

Current card counts are rendered from the verified projection. Historical
signed cards without count markers remain byte-identical on the 137-row replay
path. This contract change approves only structural handle projection: candidate
content review remains pending and training, promotion and execution authority
remain NONE. Protected source admission and explicit one-target publication with
immutable provider readback remain separate requirements.
