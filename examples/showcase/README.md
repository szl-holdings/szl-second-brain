# Synthetic Second Brain showcase

This is a **model-free, offline, synthetic software demo**. Its 17 freshly authored
fictional records contain no collected corpus, private graph, user data, model
weights, or training material. Four records intentionally fail the demo's rights
policy; 13 enter the index. Fixture source IDs and dates describe fictional
documents, not real-world attestations. All outputs grant authority `NONE`.

Run from this repository's root with Python 3.11 or later. The demo uses the
existing Python retrieval and hydration code and the standard library; it needs
no dependency installation, model download, inference server, API key, network,
or paid service. This directory is a source-checkout example, not part of the
published wheel.

```sh
python -m examples.showcase "What is aster beacon's status?"
python -m examples.showcase "How is aster beacon connected to cobalt archive?"
python -m examples.showcase "What is moss gallery's status?"
python -m examples.showcase "prove Lambda Conjecture 1"
python -m examples.showcase --evaluate
python -m examples.showcase --html > showcase-results.html
```

To deliberately regenerate the two committed review artifacts, run
`python -m examples.showcase.record`. This writes only `baseline.json` and
`index.html` in this example directory and also records hashes of its Python
source files and the reused corpus/retrieval/hydration modules, normalized to LF.
It does not publish anything.

Open [the committed static result page](index.html) locally to inspect the frozen
results, exact citations, source dates and hashes. Its silver/violet evidence
map has 7 entity vertices and 5 cited, explicit directed edges; the source cards
contain exactly the 13 admitted records. `SYNTHETIC / UNVERIFIED` remains visible.
Keyboard-accessible local links connect edges and answers to their source cards.
An open text list repeats every edge, and native disclosure controls reveal hashes.
The page has no scripts, external assets, network requests or interactive server. The CLI prints JSON;
`--k` changes the lexical candidate count within 1–12. Abstention is a valid JSON
result and exits successfully. Invalid CLI usage exits with code 2.

The accepted grammar is deliberately narrow and case-insensitive:

- `fact <entity> / <predicate>` or `What is <entity>'s <predicate>?`
- `path <entity> -> <entity>` or `How is <entity> connected to <entity>?`

All other questions abstain. This is not general language understanding. Search
returns lexical candidate IDs; a matching word does not establish an answer.
Facts must match explicit structured statements and be offered in the lexical
results. Conflicting admitted statements cause abstention, even if only one is
in the top-k window. No latest-date-wins policy is inferred.

Paths use recorded, directed, positively stated fixture edges, at most three
hops. A path explains connectivity only: it does not imply a new transitive
relationship, causality, proof, or authority. Reverse, absent, denied and
over-budget paths abstain. Source text—including injection-like strings—is
evidence data, never an instruction to the program.

The [measured baseline](baseline.json) and [design and limitations](../../docs/showcase.md)
describe 3 development and 24 evaluation queries. They are frozen,
developer-visible regression fixtures with disjoint groups, **not an independent
held-out model benchmark**. No production-readiness, novelty, AGI, model-quality,
training-eligibility, or Conjecture 1 proof claim is made.

```sh
python -m pytest tests/test_showcase.py tests/test_showcase_evaluation.py tests/test_showcase_visuals.py
```

The layout includes narrow-screen and reduced-motion CSS. The map scrolls inside
its own focusable region to preserve readable labels; the adjacent text list
needs no horizontal scrolling. Structural checks cover the intended
320/375/768/1440 viewport ranges, but browser-rendered layout has **not** been
visually verified because local-file preview is blocked by browser policy.

Tests require the repository's existing test environment. The demo itself does
not inspect credentials or accept alternate input file paths. Its only content
reads are the bundled fixtures and its own short-lived admitted corpus. The
in-memory constructor is a trusted local test seam, not an untrusted upload API.
