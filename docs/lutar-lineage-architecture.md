# Lutar evidence lineage: shared semantics, visible assurance limits

## Implemented scope

The new `/lutar` HTML page, `/api/v1/lutar-lineage` JSON endpoint and
`lutar_lineage` section of the existing Anatomy feed use one deterministic
projection of the existing byte-bound public Lutar reference. The main console
links to the page. The Anatomy projection reuses its already-read reference;
it does not read a second potentially different source snapshot.

The contract has one source-document node, eight claim-handle nodes and 24
carrier-name nodes, with DECLARES and NAMES_CARRIER relationships. The edge
names deliberately do not assert proof, causality, runtime implementation,
training completion or model qualification. This is one pinned reference, not
an estate census. No claim body, private Brain content or credentials are added.

`scenario=withhold-source` is an in-memory evidence-loss rehearsal. A valid
observed source still produces a successful HTTP response describing the
hypothetical projection, but `effective_reference_ready=false`, zero supported
claims/carriers, and an additional unavailable source gate. Missing actual
source bytes produce HTTP 503 in both API and HTML. Neither scenario changes
files, providers, controller ownership, authorization or training state.

## Tested contract properties, not new Lean theorems

- One local source read per request; a deterministic digest covers the complete
  public projection. HTML embeds that same payload, and Anatomy preserves it.
- Withheld evidence can only reduce support. The withheld node/edge sets are
  subsets of the observed projection, and its open-gate set is a superset.
- Source identity is separate from proof replay, mathematical-meaning review,
  runtime refinement and weight-bound evaluation. Unmeasured proof coverage is
  null/unavailable, not zero successes out of completed work.
- All projections retain NONE training, promotion, execution and merge authority.
- Public routes recheck source bytes; no stale pass is cached. The reference
  remains a pinned snapshot, not an upstream freshness measurement.
- The renderer escapes values and needs no JavaScript or external resources.
  Its response retains the existing restrictive CSP and no-store semantics.

The local producer-consistency check is not an externally supplied receipt
verifier or cryptographic signature verification. SHA-256 identifies content;
it is not a signature or independent attestation. No claims are made about
performance, model quality, novelty or a general-purpose fault-propagation engine.

## Research transfer, with explicit boundaries

### Palantir: common objects, permissions and dependency visibility

The Ontology architecture combines data, logic, actions and security. Workflow
Lineage exposes dependencies and lifecycle information. OSDK connects those
contracts to applications. Here the adaptation is a small typed evidence graph
shared by backend and UI, with no action authority. No Palantir code or package
is copied or installed.

Sources:
- https://www.palantir.com/docs/foundry/architecture-center/ontology-system
- https://www.palantir.com/docs/foundry/workflow-lineage/overview
- https://github.com/palantir/osdk-ts
- https://blog.palantir.com/building-with-palantir-aip-the-ontology-software-development-kit-823fe5ac7aae

The associated official YouTube lesson was located, but no transcript was
available through the research tool. This design relies on the written
technical companion, not a claim to have watched or transcribed the video:
https://www.youtube.com/watch?v=vSJ5H00V7Es

### NVIDIA: separate observation, execution and evaluation

NVIDIA's current migration guide deprecates NeMo Agent Toolkit from October
2026, with end-of-life at year end. It separates Relay (observation/middleware),
Fabric (execution adapters), and Helix (evaluation/optimization). The design
lesson is separation of responsibilities; none of these packages is installed
here. The evaluation article distinguishes successful tool calls from completed
end-state outcomes, motivating real packaged HTTP acceptance rather than counts
of source tests alone.

Sources:
- https://docs.nvidia.com/nemo/agent-toolkit/1.9/resources/migration-guide.html
- https://developer.nvidia.com/blog/how-to-evaluate-ai-agents-from-tool-calls-to-task-completion/

### LangGraph: unknown outcomes are not permission to repeat effects

LangGraph documents durable idempotency keys and reconciliation after a missing
acknowledgement. This projection has no side effects to retry. Any later agent
adapter must retain controller ownership and status reconciliation instead of
turning a read-only view into a competing executor. No LangGraph runtime or
retry loop is needed or added for this feature.

Sources:
- https://docs.langchain.com/oss/python/langgraph/fault-tolerance
- https://github.com/langchain-ai/langgraph

### GraphRAG: useful retrieval is not formal proof

The GraphRAG paper builds an entity graph and community summaries for corpus-wide
questions. Its extraction step is abstractive and may describe relations not
explicit in the source. Such generated edges can be useful research candidates;
they must remain separate from exact source declarations and checked proof terms.
This implementation uses only the latter document's declared identities; it is
not a GraphRAG implementation or benchmark.

Sources:
- https://arxiv.org/html/2404.16130v2
- https://github.com/microsoft/graphrag

## Release and integration

The existing Space include manifest adds only the two runtime modules and stays
`publish=false`. Existing CI phases are extended to exercise the new UI/API/feed
through the built image and installed wheel. A dedicated loopback check launches
and reaps only its own server on an ephemeral port. It does not contact providers.

This change is based on source revision
`1647f07cb9bd4b9b3e23efe6fb5b3388144116e6`. Current-head reconciliation, owner
review, native Linux/container CI, expected-parent publication and public runtime
readback remain release gates. Other operators' later work must be reconciled,
not overwritten. Local validation is not deployment.

## Research hypothesis for a subsequent experiment

A useful next experiment would measure whether exact, source-bound abstention
context reduces unsupported claims when evidence is withdrawn or assumptions
are broken. Compare matched-budget baselines with held-out formula families,
report denominators and preserve weight/data/harness identities. The existing
scope-challenge PR is a separate development artifact, not merged into this
feature or admitted to training by it. No new model is evaluated or trained here.
