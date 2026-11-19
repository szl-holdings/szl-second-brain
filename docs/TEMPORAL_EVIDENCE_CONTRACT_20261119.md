# Offline temporal-evidence lifecycle contract — 2026-11-19

**Status: additive source prototype; `UNSIGNED_ADVISORY_ONLY`; no runtime wiring or production-readiness change.** `second_brain/temporal_evidence.py` checks bounded metadata and temporal graph structure. It does not retrieve, generate, train, deploy, authenticate an issuer, adjudicate legal rights, or establish semantic support. Existing HIRAG, corpus admission, hybrid retrieval, API readiness, and release gates are unchanged.

## Research basis and scope

- Yang, You, Zheng, and Peng, [“Lifecycle Faithfulness for Grounded Retrieval-Augmented Generation: Benchmarks, Evaluation, and the Vera-Life Controller”](https://aclanthology.org/2026.groundlm-1.18/), GroundLM at ACL, October 2026, pp. 211–240, [DOI](https://doi.org/10.18653/2026.groundlm-1.18), define lifecycle faithfulness using semantic support, target-time validity, non-supersession, and provenance. Their controller includes answer, stale-warning, conflict-explanation, retrieval, and abstention actions. This prototype borrows the *problem decomposition and state vocabulary*, not code or results. It implements only declared-time/link checks; semantic support and authenticated provenance remain unproven. The citation and its metadata are themselves research evidence that can become stale or superseded and must be rechecked before later claims.
- [Meta FAIR CRAG](https://github.com/facebookresearch/CRAG) (Yang et al., 2024) includes `query_time`, static through real-time temporal dynamism, and distinguishes incorrect answers from missing answers. This motivates evaluating stale/future/conflict failures separately from abstention rather than treating every cited response as reliable. No CRAG code, questions, answers, mock APIs, or dataset rows are copied here; its noncommercial dataset terms are not silently relicensed or assumed to authorize an SZL benchmark.
- [SLSA v1.2 artifact verification](https://slsa.dev/spec/v1.2/verifying-artifacts) calls for signature verification against roots of trust, artifact-subject binding, and expected builder/provenance fields. Accordingly, **a SHA-256 digest is a checksum, not a signature**. The ledger recomputes metadata digests but has no keys, signed envelope, issuer policy, trusted builder, or verified source statement.
- [NVIDIA Dynamo’s architecture](https://docs.nvidia.com/dynamo/latest/knowledge-base/overview) separates request, control, and state concerns. The analogous conceptual boundary here is: an evaluation request supplies `claim_id` and `as_of`; fixed limits and the rights allowlist are control policy; immutable-by-convention evidence metadata is ledger state. No Dynamo component is used, and no inference or serving behavior is implied.

## Input and integrity contract

A ledger accepts a JSON-like Python `list` of at most 256 records. Every record has exactly these fields:

| Field | Contract |
|---|---|
| `evidence_id`, `claim_id`, `source_handle` | Lowercase namespaced IDs with prefixes `evidence:`, `claim:`, and `handle:`; ASCII body `[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?` |
| `content_sha256` | Exactly 64 lowercase hexadecimal digits; a declared content binding, not content verification |
| `recorded_at`, `valid_from` | Finite `int` or `float`; booleans, strings, NaN, infinities, and oversized integers are invalid |
| `valid_until` | A finite real timestamp or `None` for an open-ended interval |
| `rights` | Bounded machine-readable string; only `apache-2.0`, `mit`, `cc-by-4.0`, and `bsd-3-clause` pass the prototype rights axis |
| `supersedes`, `contradicts` | Lists of at most 32 unique evidence IDs; the complete ledger has at most 1,024 declared links |
| `metadata_sha256` | Recomputed digest over the fixed metadata below |

For evidence \(e\), let \(J\) be UTF-8 JSON with sorted object keys, separators `,` and `:`, no NaN/Infinity, and `ensure_ascii=False`. The digest-bound object is

\[
M_e = \{evidence\_id, claim\_id, source\_handle, content\_sha256,
recorded\_at, valid\_from, valid\_until, rights,
sort(supersedes), sort(contradicts)\},
\]

and the required check is

\[
e.metadata\_sha256 = \operatorname{SHA256}(J(M_e)).
\]

Link order therefore does not change the digest. Numeric representations remain JSON-bound (`1` and `1.0` are distinct representations), while temporal comparisons use their numeric values. The ledger digest is the SHA-256 of canonical JSON containing the schema and evidence metadata digests sorted by evidence ID.

Construction is **all-or-nothing**. It rejects malformed fields, duplicate evidence IDs, duplicate links within one record, missing references, self/cross-claim links, and directed supersession cycles. Contradiction is undirected: a declaration on either endpoint suffices, reciprocal declarations denote one edge, and a contradiction triangle is a conflict rather than a supersession cycle. Records contain no claim or evidence body. Receipts expose evidence IDs and metadata digests, not source handles or content digests; errors do not echo rejected values. Callers must still protect their input records because this module cannot erase caller-owned objects.

## Temporal and zero-veto semantics

Validity is half-open:

\[
I_e(t)=1 \iff valid\_from_e \le t \land
(valid\_until_e=None \lor t < valid\_until_e).
\]

Thus the start is included and the end is excluded. Independently,

\[
R_e(t)=1 \iff recorded\_at_e \le t, \qquad
L_e=1 \iff rights_e \in \mathcal{L}_{allow}.
\]

`recorded_at` prevents information first observed after `as_of` from leaking backward in time. A record can have a currently valid interval but still fail because its observation is in the future.

Supersession edges point from the newer record to each record it explicitly supersedes. Let \(Q_s(t)=R_s(t)I_s(t)\), deliberately without a rights requirement. \(S_e(t)=1\) iff at least one direct-or-transitive successor \(s\) has \(Q_s(t)=1\). A future successor therefore does not supersede early. An unauthorized successor can still establish the declared lifecycle transition, but cannot itself become a candidate.

For evidence attached to the requested claim, define

\[
V_e(t)=L_eR_e(t)I_e(t)(1-S_e(t)), \qquad
P(c,t)=\{e: claim_e=c \land V_e(t)=1\}.
\]

This is the zero-veto rule: any failed rights, observation, interval, or supersession axis makes \(V_e=0\); there is no relevance score or weighted average that can compensate. Metadata validity is also mandatory, but is guaranteed by all-or-nothing construction rather than averaged at query time. This is conceptually compatible with HIRAG’s zero-veto reasoning but does **not** calculate or replace HIRAG \(\Lambda\), invoke its trust anchor, or wire into its runtime.

Within \(P(c,t)\), explicit current conflicts are

\[
X(c,t)=\{(a,b):a,b\in P(c,t),\ a<b,\ a\ contradicts\ b\}.
\]

The claim-level decision is deterministic:

1. \(X\ne\varnothing\): `EXPLAIN_CONFLICT`; list sorted conflicting pairs and select nothing.
2. Otherwise \(|P|>1\): `ABSTAIN / TEMPORAL_AMBIGUOUS_CURRENT_EVIDENCE`; multiple unlinked current versions are not silently ranked.
3. \(P=\{e\}\): `CURRENT_CANDIDATE`; expose only \(e\) as the candidate.
4. \(P=\varnothing\): abstain for otherwise-current rights-ineligible evidence; otherwise abstain for future evidence; otherwise `WARN_STALE` when stale evidence exists; otherwise abstain for superseded/no-current evidence.

Every per-evidence receipt reports all five axes, failed-axis names, and `zero_veto_pass`. A stale item can therefore retain `WARN_STALE` even when a separate unique current item makes the claim-level state `CURRENT_CANDIDATE`. Rights-ineligible, stale, or future records cannot manufacture a claim-level ambiguity/conflict. A claim-level stale warning never includes a current candidate.

`CURRENT_CANDIDATE` means only “one record passed this declared structural policy at this explicit time.” Every receipt also states `semantic_support=NOT_EVALUATED`, `signed_provenance=NOT_ESTABLISHED`, `grounded_navigation=NOT_ESTABLISHED`, `runtime_integration=NOT_APPLIED`, and `execution_authority=NONE`. It is not an answer, citation-support judgment, navigation grant, training grant, or signed provenance receipt.

## Explicitly unproven and unchanged

- No accuracy, recall, lifecycle-faithfulness, latency, or quality improvement has been measured on SZL data or an external benchmark.
- Declared timestamps and links can be wrong, incomplete, or malicious. Digest agreement detects metadata drift after hashing, not truthful authorship or real-world time.
- No source content is opened or checked against `content_sha256`; no legal review verifies the declared rights string; no entity resolution or semantic contradiction detection is performed.
- Open-ended validity means no declared end, not perpetual truth. Missing evidence, unknown claims, malformed queries, and non-finite `as_of` fail closed.
- No production module was edited. Existing HIRAG admission behavior and default `NOT_APPLIED` integration are unchanged; no readiness flag, deployment gate, ACL, model, training path, or release authority was changed.

## Proposed SZL measured ablations — not yet run

Freeze a rights-cleared, source-versioned synthetic/public fixture with claim IDs, independently reviewed `as_of` labels, and current, past, stale-only, update, conflict, multi-hop, future-observation, and unknown-rights cases. Keep source ordering and ground-truth denominators fixed. Use only generated metadata fixtures unless external dataset rights have been separately approved.

Compare paired arms on exactly the same records: **A0** no lifecycle decision; **A1** observation and half-open interval only; **A2** A1 plus supersession; **A3** A2 plus contradiction/ambiguity handling; **A4** full rights zero-veto. Secondary ablations remove `recorded_at`, remove transitive rather than direct supersession, and reverse either-direction contradiction semantics. Do not tune on the test split.

Predeclare per-claim counts and paired deltas for wrong-current rate, stale/future/superseded selection rate, current-candidate recall, conflict-explanation recall, false-conflict rate, ambiguity abstention, relevant-evidence refusal, and candidate coverage. Separately report unknown-rights refusals and stale warnings; never fold them into a single “accuracy” number. Include adversarial boundary cases exactly at start/end/observation times and a negative condition where corroborating but unlinked records cause ambiguity or a rights veto removes relevant evidence. Report p95 construction/evaluation time and bounded-input refusal behavior without presenting synthetic timings as service latency.

Only after those offline measurements should a separately reviewed experiment consider placing a resulting candidate into the existing HIRAG admission input. That later experiment must preserve the original ranking denominator, compare flat/graph/HIRAG arms independently, and obtain real signature and rights verification before making provenance or production claims.

## Offline verification

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_temporal_evidence.py -v
git diff --check
```

The targeted suite contains 42 standard-library `unittest` tests covering lifecycle states, graph/temporal attacks, strict types and IDs, digest tampering, bounds, determinism, input mutation, privacy labels, and absence of network/wall-clock calls. Passing tests establish this local contract only.
