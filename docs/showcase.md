# Synthetic retrieval showcase: evidence and limits

## Scope and integration

The [example](../examples/showcase/README.md) is an additive source-checkout demo
based on main `a477d550276f63fdcdafca6efa05e655fcca0ba9`. It does not change public
API contracts, runtime defaults, dependencies, the publisher, frontier, training,
or data directories. At the 2026-10-06 reconciliation, open PRs #39–44 did not
touch `examples/showcase/`, `tests/test_showcase*.py`, or `docs/showcase.md`.
PR #43 was at `e69f951744784af736bdd271280f2de2c9a39815`; #44 was at
`675a911ddf62cf22daa08bf492c87b3277bb36d8`. The root README is left to the existing
local-memory work; this example has its own README.

`SecondBrainIndex` supplies the existing deterministic TF/IDF-like ranking with
term-frequency saturation. It has no document-length normalization and is not
standard BM25. Scores indicate lexical overlap. This example configures no dense
provider, reranker, model, tokenizer download, inference, or training process.

The adapter validates the fixed synthetic records, then writes only admitted
rows to a temporary JSONL projection. It supplies that explicit path and its
digest to `SecondBrainIndex` and `AuthorizedHydrator`, captures their in-memory
generations, and removes the temporary directory. The hydrator authorizer is
restricted to the synthetic principal, tenant, policy revision, and admitted
node/source pairs. It grants no access to the repository's existing corpus.
Environment variables cannot select a different showcase input.

The local fixture manifest pins bytes. Each citation binds a record ID, synthetic
source ID, source family, ISO date, exact statement, text SHA-256 and complete
fixture revision. These hashes establish consistency with the reviewed fixture,
not independent authorship, legal authorization, truth, or freshness. The
constructor also checks its revision against the fixed fixture-authoring JSON
encoding. Test variants receive distinct revisions.

## Rights and authority

Only the exact rights map below is admitted. Booleans must be literal booleans;
strings, integers, missing fields, extra grants and other values fail closed.

```json
{"synthetic": true, "private": false, "retrieval": true, "display": true,
 "training": false, "basis": "authored-for-demo"}
```

The fixture includes denied retrieval, private, missing-basis and denied-display
edge cases. These remain fictional negative controls; no actual private content
is present. Malformed record structure, duplicate IDs or claims without an exact
statement reject the entire generation. Structurally valid denied rows are
excluded before indexing or hydration. Structural checks and rights labels are
local demo policy, not a general rights-clearance service.

All raw fixture content is freshly authored for this example. None of the
existing 575 public chunks, quarantined raw graph, attribution records or legacy
training rows are used. No training permission follows from a retrieval or
display permission. No model, dataset or provider release is performed.

## Answer and navigation contract

The grammar is documented in the example README. Inputs are limited to 300
characters, 1–12 lexical candidates, 64 records, 8 claims per record, and
128 KiB per fixture file. The manifest has a separate 4 KiB bound. The shipped
bundle has 17 records, 13 admitted, and 27 queries.

A supported fact must have one object across all admitted records for the exact
subject/predicate and at least one matching record in the lexical result. Its
selected citation is hydrated and checked against the exact structured statement.
Conflict checking examines all admitted records, not just retrieved candidates.
Unsupported grammar, unknown facts and absent candidates abstain.

Breadth-first traversal uses only explicit directed fixture edges, a stable
ordering and a three-hop cap. Every emitted step names its supporting record and
has a matching citation. It searches the bounded admitted edge set independently
of lexical top-k retrieval. It does not extract edges from prose, invert them,
resolve aliases, infer causation, or turn a connectivity path into a theorem.
No zero-hop path is presented as evidence. The schema has no negative-edge
assertions; adding contradiction semantics for edges would require a new design.

Abstention has `answer: null`, empty citations and empty steps. It may retain
public synthetic lexical candidate IDs to make overlap errors visible. Source
text cannot change the grammar, policy, selected claims or output authority.
For example, both `iris lemma is proved` and `iris lemma is not proved` retrieve
the same candidates under the inherited stop-word policy, but both abstain as
unsupported assertions. The explicit proof-status question returns the fixture's
`not proved` statement. `prove Lambda Conjecture 1` abstains; Conjecture 1 remains
unproved by this work.

## Frozen software evaluation

The manifest and tests pin the 2026-10-05 fixture bytes. Development contains
3 cases; evaluation contains 24. Source family, entity group and query-template
identities are disjoint between the two partitions. Entity/source groups in
the records are also disjoint. All fixtures are visible to implementers; the
partition does not establish independent or blinded generalization. There is no
training step and no training-overlap gate.

The evaluator checks a closed output schema and the actual selected citations,
not just whether a relevant ID appears anywhere in the retrieved list. Its gold
answers, relevant records, ordered paths and negative reasons are explicit in
`queries.json`. Malformed JSON, duplicate keys, missing outputs, exceptions and
invalid schemas remain failures in the original denominators. Empty metric
denominators are reported as `null`, not perfect scores.

The committed baseline is a deterministic software measurement at k=3:

`python -m examples.showcase.record` reproduces the baseline and page locally.
The receipt records LF-normalized hashes of the example's Python sources and
the reused corpus, retrieval and hydration source modules. Input fixture hashes
always bind raw bytes. The source-base field describes this feature's integration
base; the per-file hashes identify the implementation actually recorded.

| Evaluation metric | Result | Denominator |
| --- | ---: | --- |
| Parse and output-schema validity | 24/24 | All evaluation cases |
| Citation/record integrity | 24/24 | All cases; empty abstentions have no citation to violate |
| Lexical micro Recall@3 | 9/14 (64.3%) | Required record occurrences over the 10 cases with retrieval gold |
| All-required lexical Recall@3 | 8/10 (80%) | Cases with at least one required record |
| Selected citation correctness | 7/7 | Supported-answer cases, exact selected IDs and metadata |
| Supported answer coverage | 7/7 | Supported cases, including answer, path and citation correctness |
| Supported navigation | 3/3 | Directed-path cases with complete ordered steps |
| Correct abstention | 17/17 | Unsupported/conflicting/denied cases, including expected reason |
| Unsafe or invalid negative output | 0/17 | Negative cases; invalid schemas count as failures |

Retrieval metrics are independent of answer/citation correctness: replacing a
selected citation with another valid fixture citation leaves lexical recall
unchanged while failing citation correctness. Bad schemas or unknown retrieval
IDs get zero retrieval credit. Graph traversal's complete paths are not evidence
that lexical retrieval recovered their intermediate records.

Controls cover unknown entities/predicates, conflicting dates, reversed and
disconnected paths, denied edges, hop limits, unsupported proof, negation,
injection text/query, trailing instructions, empty queries, rights types,
tampered bytes and unsupported citations. Tests also remove and rewire an edge,
mutate selected citations despite correct retrieval, supply malformed outputs,
and use an always-abstain predictor that necessarily fails supported coverage.
Those are correctness controls, not comparative research results.

The offline runtime test blocks sockets, DNS, subprocesses and shell execution;
allows content reads only from the three fixture files and the temporary corpus;
and rejects credential environment reads. It sets both legacy corpus environment
overrides to a forbidden sentinel and verifies they are not opened. The guard
covers demo construction, all queries, evaluation and HTML rendering after normal
Python imports. This is scoped software evidence, not an operating-system sandbox
certification. The static page escapes text and forbids external resources via
Content Security Policy.

## Static evidence view

The renderer uses native inline SVG, CSS, fragment anchors and disclosure
elements. There is no JavaScript, canvas, GPU framework, CDN, remote font, new
dependency or external resource/navigation link. `render()` delegates presentation to
`view.py`, whose hash is included when `record.py` regenerates the artifacts.
The renderer checks that its admitted projection and report share the same
fixture revision before displaying them together.

The graph has seven entity vertices and five recorded directed edges from the
admitted fixture. Separately, the source catalog has exactly thirteen admitted
record cards. Record count and entity count are labeled distinctly; no artificial
record-to-record relationship is inferred. Every edge has its original subject,
predicate, object and source record; every source link resolves to an admitted
card. Removing a row's admission removes its card, edge and any now-unreferenced
entity. Excluded record identities and statements are absent from both evidence
views. Negative-control questions remain visible as user queries in the result
section; they do not disclose excluded source content.
An evaluated prediction with invalid schema or evidence renders as a neutral
failure card containing only the query and failure label. Its proposed answer,
citations, record IDs and links are not echoed, including denied-record and
wrong-generation citation attempts.
Integrity-valid predictions must also pass citation selection, answer, path and
complete-case checks before the renderer presents them as successful results.
Failures display **UNQUALIFIED OUTPUT** and identify the unsuccessful checks.
Their raw prediction is retained as escaped JSON in a closed disclosure labeled
for review only; its claimed status, answer and citations are not rendered as a
validated answer or as active source links. These presentation checks consume
the existing evaluator results without changing its scoring or denominators.

The restrained silver/violet palette keeps the `SYNTHETIC / UNVERIFIED` state
visible. The map has a title, description and open text equivalent containing
all five edges. A skip link, ordinary fragment links, focus outlines and native
disclosure controls support keyboard use. The graph scrolls within its own
focusable region rather than shrinking labels to unreadable sizes. Source and
result cards collapse to single columns on narrow screens; long hashes wrap.
CSS includes reduced-motion overrides without default animation.

Tests validate exact record/entity/edge counts and evidence bindings, denied-row
exclusion, local anchor targets, SVG syntax and bounded node geometry, escaping,
the no-script/no-external-asset contract, text-color contrast against declared
surfaces, and overflow/breakpoint/reduced-motion structure. The intended viewport
checks cover 320, 375, 768 and 1440 pixels structurally. These are **not actual
browser layout or accessibility certification**. Browser policy blocked local-file
preview; it was not bypassed, and the rendered appearance remains unverified.

## Future research experiment — not executed

The current tiny, developer-visible fixtures do not qualify a model or establish
calibrated risk, retrieval superiority, statistical acceptance, or latency gains.
The proposed engineering targets below were supplied before this demo's measured
run and all remain **INCONCLUSIVE** as research acceptance claims:

- Zero observed integrity escapes and at least 80% supported coverage.
- A one-sided 95% upper bound of at most 5% on unsupported false navigation,
  conditional on independent sample adequacy and a prespecified sampling model.
- At least five percentage points of all-required Recall@5 improvement, with a
  group-aware confidence lower bound above zero.
- p95 latency no greater than twice the chosen baseline under a pinned environment.

A later rights-qualified experiment should freeze separate calibration and test
source/entity/template groups and compare the existing lexical scorer, standard
BM25, a support-threshold policy, always-abstain, shuffled evidence and an oracle
reference. Edge-removal and rewiring ablations should isolate graph effects.
Repeated templates and correlated records must not be counted as independent
samples. Any such comparison needs new evidence; these thresholds are not source
paper guarantees and were not passed by 17 successful negative fixture cases.

[Learn then Test](https://doi.org/10.1214/24-AOAS1998) is a reference for a later
risk-calibration design. [HippoRAG 2](https://arxiv.org/html/2502.14802v2) motivates
testing structured retrieval separately from ordinary factual retrieval; this
example implements neither its models nor its Personalized PageRank pipeline.
The [GraphRAG project](https://github.com/microsoft/graphrag) is a possible future
comparison, not an installed dependency. No results from those systems are
transferred to Second Brain or claimed as this demo's results.

Legacy handle-presence retrieval checks, navigator generation availability,
later model evaluation failures and this demo's software results are different
evidence. This change does not repair, rerun or supersede legacy model evaluations
or their failed release gates. It supplies no model weights or training recipe.
