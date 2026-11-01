# Python integration review and research decisions

Observed source baseline: `45ce374ef4694a271859cb2b0e43870e4c07a9de`.
Research reviewed 2026-11-01. This is a bounded Second Brain implementation;
it does not certify the other SZL services or a deployed provider revision.

## Gaps and repairs

| Gap in the inspected baseline | Consequence | This change |
| --- | --- | --- |
| Three progressively imported application modules | Launch command determines which routes are registered | One packaged `second_brain.web:app`; old module names are compatibility entry points |
| Hologram independently calls retrieve and plan | Repeated work; displayed handles and plan are not explicitly bound to one result | One query transaction shared by Python console, hologram and JSON API |
| JSON bodies manually coerced or silently clipped | Lists, noninteger `k`, and malformed handles can crash; clients cannot distinguish rejected input from changed input | Strict bounded Pydantic contracts, explicit errors, documented OpenAPI request schemas |
| Caller-supplied plan handles treated as grounding | A fabricated node with an overlapping note can be cited | Only unique, exact handles from the current retrieval may be selected |
| `/readyz` checks only the base corpus | Frontier/refinement failures can remain invisible | Component readiness and HTTP 503 for missing required public services |
| Newer retrieval/frontier functions absent from the primary UI | Formula/research candidates and ranking receipts are hard to inspect | Python-rendered forms, separate corpus/review panels, source revisions, digests, receipt inspection |
| Web app and HTML outside wheel package | Installed library lacks a complete web entry point | Packaged routers, console and hologram assets; installed-mode verification outside source tree |

Baseline reproductions: POST `[]` to retrieve and `k="many"` to plan return
HTTP 500. A fabricated `made-up` handle with note `formula` is accepted by the
old plan endpoint. The new tests require bounded client errors and reject
fabricated, duplicated or altered handles. The combined receipt binds query,
corpus generation, evidence, handles, ranking receipt, review handles and plan.
It is a content checksum, explicitly unsigned; it is not an attestation.

## Reference systems and what they teach us

These are relevant primary-source reference implementations, not a claim that
one product leads every metric. The following adoption decisions are our
engineering assessment, not results reported by those projects.

### FastAPI: explicit contracts

[Request models](https://fastapi.tiangolo.com/tutorial/body/) connect validation
and OpenAPI. [Response models](https://fastapi.tiangolo.com/tutorial/response-model/)
can validate and filter output. We adopt strict shared request models immediately.
The existing heterogeneous receipt dictionaries remain explicit public
projections; this patch does not claim that every legacy response has a typed
schema. Next qualification should add versioned response schemas and consumer
compatibility tests before exposing more fields.

### Reflex: Python UI state

[Reflex architecture](https://reflex.dev/docs/advanced-onboarding/how-reflex-works/)
uses Python state handlers with a compiled React frontend and WebSocket events.
That is useful for rich interactive state but introduces a frontend build and
connection lifecycle. This read-only evidence workflow needs forms, tables and
receipts, so the implemented UI renders directly in Python and shares service
functions with the API. It works without JavaScript or an additional framework.
Choose Reflex later if persistent interactive state justifies those costs.

### Microsoft GraphRAG: retrieval by question type

[Query modes](https://microsoft.github.io/graphrag/query/overview/) distinguish
entity-specific local retrieval from corpus-wide questions.
[Global search](https://microsoft.github.io/graphrag/query/global_search/) applies
map/reduce over community reports. Its
[implementation](https://github.com/microsoft/graphrag/blob/main/packages/graphrag/graphrag/query/structured_search/global_search/search.py)
uses bounded concurrency and accounts for model calls and tokens by stage.
SZL should preserve that cost accounting and explicit mode distinction.
Adding a graph drawing to BM25 does not implement GraphRAG. A real integration
needs admitted entity/edge/community artifacts, source bindings and a qualified
generation provider. None are silently inferred by this patch.

### HiRAG: connect local and global evidence

The [HiRAG paper, v3](https://arxiv.org/html/2503.10150v3) constructs hierarchical
knowledge using embedding clusters and summary entities. Its retrieval includes
bridge paths between local evidence and community context. This is a useful
experimental direction for cross-organ SZL queries. The paper also reports
substantial indexing cost and identifies query relevance limitations in its
relation ranking. Its benchmark wins are not SZL measurements. Compare flat,
hierarchical and bridge-ablated variants on our fixed query set before adoption;
retain every generated summary's contributing source IDs.

### LangGraph: persisted workflows

[Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)
persist graph state at super-step boundaries. Synchronous durability commits
before continuing; asynchronous and exit modes have different crash windows.
Replay can re-execute later API calls. SZL repair jobs therefore need admission
records, operation IDs and idempotent external effects in addition to checkpoints.
A local JSON checkpoint or an in-memory queue is insufficient evidence for
exactly-once provider updates. This query console is read-only and introduces no
repair executor; durable execution remains a separate integration requirement.

### NVIDIA NeMo Guardrails: checks at each boundary

[Rail categories](https://docs.nvidia.com/nemo/guardrails/configure-guardrails/yaml-schema/guardrails-configuration)
separate input, retrieval, dialog, execution and output checks. We apply that
separation to request validation, retrieved-handle identity, planning and public
output. A policy label in a response cannot substitute for an enforced check.
Model-based rails, if adopted, must supplement deterministic authorization and
digest validation; they do not grant training or deployment authority.

### Reciprocal-rank fusion: retain a reproducible baseline

The [original RRF paper](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf)
combines ranks using the sum of `1 / (k + rank)`, with `k=60` in its experiments.
The existing hybrid engine already supports weighted RRF and source limits.
Preserve this baseline while testing SZL variants. RRF values order candidates;
they are not calibrated probabilities that an answer is correct.

## Where SZL mathematics can be tested

The [canonical locked claim contract](https://github.com/szl-holdings/lutar-lean/blob/990526e23d6d35a7b4109a8b67b171b0af3785ce/claims/locked-formulas.v1.json)
defines F1, F4, F7, F11, F12, F18, F19 and F22. The executable
[formula metadata](https://github.com/szl-holdings/szl-formulas/blob/fe5f8d8dc034a929059e00fd3524e7f3dbbcd434/torch-ext/szl_formulas/metadata.json)
uses a separate callable namespace. Bind each candidate runtime use to the exact
symbol, source revision, input domain, Lean declaration and refinement evidence.

- F4 can check a graph encoded with strictly backward natural-number edges;
  it does not establish Byzantine consensus or the safety of arbitrary edges.
- F7 describes an in-memory list queue; retries, persistence and deduplication
  need separate runtime evidence.
- Locked F1 reflexivity does not prove stability of a production replay hash.
- The canonical Lambda contract records a counterexample to unconditional
  uniqueness under bare A1–A5. Conditional results are outside the locked eight.
  Lambda must remain advisory, never a probability or authorization gate.

Proposed experiment sequence: freeze a rights-cleared corpus and independently
label entity, cross-source, global-theme and abstention queries. Compare BM25,
qualified dense+RRF, hierarchy/bridge retrieval, then one SZL modification at a
time. Record Recall@k, nDCG@k, citation validity, abstention errors, p50/p95 latency,
indexing cost and query cost. Separate retrieval quality from generated-answer
quality. Use held-out judgments and paired uncertainty estimates; reject a gain
that trades away source integrity or the required abstention behavior. This is
an experiment design, not a completed benchmark or new theorem.

## Remaining operational gates

Public runtime remains BM25-only; no dense model, reranker or generation service
is configured. Review candidates remain unpromoted. This source change does not
provision signing keys, provider access, service URLs, distributed job storage,
or tenant authorization. Production readiness still requires exact deployed
revision readback, complete dependency checks, signing and the existing release
gates. A successful local suite or green `/health` is not estate-wide readiness.
