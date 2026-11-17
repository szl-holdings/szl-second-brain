# Evidence ecosystem: Palantir patterns, LangGraph, and NVIDIA

Research and implementation date: 2026-11-16. Source baseline:
`szl-second-brain@1647f07cb9bd4b9b3e23efe6fb5b3388144116e6`.
This extends `INTEGRATION_RESEARCH_20261101.md`; it does not replace the
canonical A11oy/Hatun execution controller or the existing SZL Nemo witness.

## Implemented vertical slice

`GET /evidence` and `GET /api/v1/evidence-graph` call the same local projection
function. It consumes one existing query transaction and rechecks the retained
Lutar reference bytes. It verifies the transaction's evidence, handles, ranking,
plan and receipt bindings before constructing bounded typed objects and links.
The UI is a server-rendered, responsive inspector with working forms, source
identities, expandable objects, links and the exact graph JSON. No client-side
mock dataset, CDN, remote script, model call or private graph is added.

Objects are corpus handles, review candidates, Lutar source references, a
software citation proposal and an unsigned view receipt. Relations mean cites,
binds or includes-reference: they do not mean proves, authorizes or executes.
A separate view manifest binds all projected objects and links plus the original
query receipt identity. Added Lutar references are not falsely attributed to the
older query checksum. The complete view receives its own digest, not a signature.

Every edge uses strictly decreasing integer ordinals, checked at runtime. This
is an F4-motivated property of this bounded reference view. It is not a proof of
Lean-to-Python refinement, semantic causality, consensus, the private Brain's
acyclicity, or a guarantee about provider workflows. F1 hash reflexivity does
not establish cryptographic security, and F7 list-queue order does not imply
exactly-once external effects. Lambda remains advisory.

Missing Lutar bytes make this view partial/unavailable without changing the
existing core retrieval service's readiness. Empty query coverage is not a pass.
Tampered evidence is rejected rather than replaced with sample data. The view
states its local-snapshot freshness basis; it is not a live estate status feed.

## Optional adapters, one shared contract

Install the reviewed versions in a separate environment:

```bash
python -m pip install -r requirements/evidence-integrations.txt
```

The file pins the three top-level SDK versions; it is not a complete transitive
hash lock. They are not required or imported by the ordinary web runtime. Relay's public
README labels it beta; upgrades require rerunning the integration contract,
not merely accepting an unbounded version range.

```python
from second_brain.evidence_adapters import make_langchain_tool, make_langgraph

tool = make_langchain_tool()
snapshot = tool.invoke({"query": "Lutar invariants", "k": 4})
graph = make_langgraph()
result = graph.invoke({"query": "Lutar invariants", "k": 4})
assert result["snapshot"] == snapshot
```

`make_nvidia_callback()` provides a real NeMo Relay LangGraph callback. Configure
Relay's scope/plugin lifecycle in the owning application, using its official
quickstart. The adapter does not discover credentials or configure an exporter.
The integration test records lifecycle events to a new local test directory,
with full payload export disabled and external network connections refused.
Telemetry can still contain sensitive metadata: private retention and a
separately reviewed exporter are required. Instrumentation does not authorize
anything. No NIM/Nemotron inference or GPU benchmark is performed here.

This read-only graph deliberately has no checkpointer. Every invocation
re-observes its source. It is not a persistent repair agent. The controller
must implement durable ownership, idempotency, admission and fresh evidence
before adding external effects; a saved graph checkpoint is not permission.

## Primary-source research and adoption decisions

These are relevant reference systems, not a ranking of all vendors. The
adoption column is SZL engineering judgment, not a vendor claim about SZL.

| Source reviewed | Supported lesson | SZL decision |
| --- | --- | --- |
| [Palantir OSDK overview](https://www.palantir.com/docs/foundry/ontology-sdk/overview) and [public OSDK TypeScript repository](https://github.com/palantir/osdk-ts) | Typed ontology objects/actions connect application logic and UI; scoped tokens coexist with user permissions | Share typed evidence identities across API, inspector and adapters; do not introduce a Foundry dependency or copy proprietary internals |
| [Palantir action submission criteria](https://www.palantir.com/docs/foundry/action-types/submission-criteria) | Action eligibility is evaluated from user, object and execution context, separately from permission to edit the action definition | Preserve A11oy/Hatun admission and human approval; no execution button or client-derived authorization in this view |
| [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), and [public implementation](https://github.com/langchain-ai/langgraph) | Checkpoints support workflow recovery; replay and external effects need explicit handling | Add a tested read-only graph now; do not create another durable controller or infer exactly-once actions |
| [NVIDIA migration guide](https://docs.nvidia.com/nemo/agent-toolkit/1.9/resources/migration-guide.html) | Agent Toolkit was deprecated in October 2026, with EOL at year-end; migration guidance separates Relay, Fabric and Helix roles | Use Relay for this new optional lifecycle integration; do not add the retiring NAT toolkit, a second execution harness or a second evaluation control plane |
| [Relay LangGraph quickstart](https://docs.nvidia.com/nemo/relay/latest/getting-started/quick-start/langgraph) and [public Relay repository](https://github.com/NVIDIA/NeMo-Relay) | Callback scopes, explicit plugin activation and flushing enable credential-free local trajectory capture | Test the actual callback against the same evidence result, with private local traces and no inference |
| [Rebedea et al., NeMo Guardrails, EMNLP 2023](https://aclanthology.org/2023.emnlp-demo.40/) | Programmable runtime rails complement model alignment; model-based checks are imperfect and introduce overhead | Keep deterministic schema, identity and authorization checks independent of model-based rails; measure any added judge's errors and latency before adoption |

Research scope: official documentation, public repository README/interface
material, and the Guardrails paper's architecture and limitations sections
(including PDF figures) were inspected. These external repositories were not
exhaustively audited. The paper's historical results are not SZL measurements
or a benchmark of current releases. NVIDIA's current migration notice concerns
Agent Toolkit, not the separate Guardrails library or SZL's deterministic Nemo.

The official [Palantir OSDK video](https://www.youtube.com/watch?v=vSJ5H00V7Es)
was located, and the official [LangGraph Essentials course video](https://www.youtube.com/watch?v=B_BCeWhyD5Q)
description was reviewed. Full transcripts were not available through this
inspection. Video discovery is not a claim that entire presentations were
watched, transcribed or absorbed into a training set.
No external research corpus was silently added to model gradients.

## Canonical SZL responsibilities

- Brain: public handle retrieval, source identities and read-only observation.
- Lutar Lean: exact theorem statements, hypotheses, checked proof scope and
  unresolved obligations. A formula handle is not a runtime authority.
- SZL Nemo: the deterministic R1-R5 / E1-E10 witness, not NVIDIA Nemotron.
- A11oy / Hatun: existing authentication, tenant rights, action admission,
  human gates, signing and postconditions. Hatun's retired standalone Space
  publisher must not be recreated.
- LangChain / LangGraph: optional application interfaces/orchestration, never
  an alternate permission source. Relay: lifecycle telemetry, not authorization.
- Living Anatomy: sanitized evidence consumer, not an autonomous decision maker.

These responsibilities were checked against canonical public Hatun source
`bcb54ebfa2d6c417c255d14207e09010dcb9139f` and SZL Nemo source
`8d32f300cdb2d39200a8e623942269acb0d304c2` on 2026-11-16.

## Research proposal: counterfactual evidence-loss analysis

A useful next experiment is to ask, for every proposed action: which exact
proof obligation, source revision, authorization or freshness observation is
missing, and which downstream decisions become invalid if one observation is
withdrawn? This extends the existing family-held-out Lutar scope challenge.

Pre-register a held-out set of missing-source, expired-observation, version-drift,
broken-premise and competing-writer cases. Compare ordinary retrieval with
source-bound retrieval and dependency-loss explanations. Measure unsupported
claim rate, correct abstention, false abstention, diagnosis precision/recall,
latency and observer cost with explicit denominators and uncertainty estimates.
Do not train on evaluation labels or imply that the runtime view itself proves
semantic dependencies. Proof-conditioned variants require independently checked
and replayable proofs before admission. No novelty or quality gain is established
by this proposal, and no training launch is authorized by it.

## Remaining release gates

The change is bounded to the inspected Brain path. It does not close all estate
audit gaps. Native CI, owner review, exact source-owned publication, immutable
provider readback, service-level authorization and runtime checks remain separate.
No paid job, provider config, signing key, private graph, security setting,
account permission, training target or background scheduler is changed.
