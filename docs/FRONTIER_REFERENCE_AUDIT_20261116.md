# Frontier reference audit — 2026-11-16

**Disposition:** engineering research, not verified comparative performance, release authority or a new theorem. These references were brought by the operator as images and followed to named primary sources where available. The five-pass GitHub census lives in owner-private evidence rather than this public repository.

## Reference-to-system decisions

| Reference | Verifiable source or boundary | SZL treatment |
|---|---|---|
| DeepMind AlphaProof Code (10 Nov 2026), Figure 1 | https://deepmind.google/documents/36/Formal_Verification_of_Signal_4.pdf | Independently approve a precise specification and retain a held-out copy; only Lean kernel plus comparator can close a proof claim. This Brain does not implement binary semantics, a comparator or proof replay. Source digests and named carriers must **not** be called proved refinements. |
| Harvard CS2680 (Fall 2026) | https://cs2680.seas.harvard.edu/ | Benchmark one task all the way from agent loop/token cost through routing, KV cache, batching, quantization and GPU. No speedup is claimed without workload, hardware, model identity, baselines, repeated measurements and quality retention. |
| AgentMemory | https://github.com/rohitg00/agentmemory | Examine capture/recall, source-linked corrections, cross-client context budgets and pruning. Their repository's retrieval benchmark is self-reported and is not SZL task accuracy. Do not import private agent sessions, tokens or raw 9,464-node graph into public Brain or model weights. |
| User-provided 'Recall Loop' image | Unverified working note supplied in this request | Useful five-state concept: read, capture, confirm, write, prune. Confirm new memories with a responsible author; keep dated immutable source and review metadata; do not silently promote agent guesses or delete source evidence. |
| TypeSafe Jev / typed decisions | https://vercel.com/changelog/typesafe-ai-jev-now-available-on-ai-gateway and https://arxiv.org/abs/2610.24929 | Candidate advisory fast router only, with deterministic allowlist, frozen action vocabulary and held-out calibration/abstention tests. A typed probability is **not** policy authorization, especially when the input is stale. |
| Microsoft GraphRAG | https://github.com/microsoft/graphrag | Retain BM25 baseline. Evaluate local/entity, global/community and bridge retrieval only with admitted edges, evidence rights, source digests and measured citation validity. Graph drawing is not GraphRAG. Repo says it is now in maintenance mode. |
| AI agent skills: Anthropic, Superpowers, gstack, Addy Osmani | https://github.com/anthropics/skills ; https://github.com/obra/superpowers ; https://github.com/garrytan/gstack ; https://github.com/addyosmani/agent-skills | Pin and audit the exact source, permissions, hooks, scripts, licenses and tool effects before borrowing ideas. SZL already has a skills repo; do not recursively install marketplace tools into governed agents. |
| ccusage | https://github.com/ryoppippi/ccusage | Evaluate local, consented session-token and cached-token accounting for agent-workload cost receipts. Separate estimated cost from billing settlement; no central upload of raw chat logs. |
| OpenAI Secure MCP Tunnel client | https://github.com/openai/tunnel-client | Research for a privately approved MCP endpoint only; it is not authorization to expose raw inference, bypass Access, or route an ungoverned laptop tool server into production. |
| YAML-based homelab topology (user screenshot) | Image reference, no reproducible source code inspected | An inventory-to-topology transform is presentation, not active network discovery. Require inventory revision, connectivity observation time and provenance for each edge; never publish private IPs, network keys or device locations. |
| Binary quantization '32x memory' social image | User screenshot; no linked benchmark checked | Float32 vector values versus 1-bit packed values have a theoretical 32:1 storage ratio *before* indexing overhead, quality loss and re-ranking. Only adopt after recall/nDCG, indexing cost, latency and sensitivity experiments. |

## SZL architecture: one immutable evidence transaction, many consumers

    source+rights+revision -> admitted handles -> query receipt
                       |                |-> /evidence read-only projection
                       |                |-> /lutar pin-bound lineage
                       |                |-> Living Anatomy observer
                       \-> independent approved spec/proof review (not in this patch)
    proposal -> Nemo PRE witness -> A11oy/Hatun authorization -> execution -> POST witness + signed evidence (external)

The existing code now implements the read-only Lutar lineage, evidence graph and optional framework adapters. These produce **content digests**, not signatures or source-authenticity proofs. They cannot execute tools, train weights, mint authoritative signed outcomes, or grant approval. External LangGraph and NeMo Relay adapters are optional; the base runtime does not gain them as required dependencies.

## Falsifiable next experiments, ordered by risk

1. **Independent source/spec comparator:** held-out approved Lean statement and dependency definitions; prove that a subtle premise mutation, source mismatch or vacuous proposition is rejected. Require independent replay and explicit scope before using PROVED.
2. **Counterfactual loss graph:** withhold source, change pinned revision, expire a telemetry probe; measure correct downstream invalidation, false abstention, recovery and source-identity integrity. Never infer runtime changes from an in-memory exercise.
3. **Memory recall on fixed development and held-out tasks:** compare baseline BM25, optional scoped graph, optional dense+RRF, and agentic retrieval under equal cost budgets. Record recall-all@k, citation validity, privacy, p50/p95 and abstention; do not import unreviewed raw private sessions.
4. **Decision-router cascade:** compare deterministic policy alone, cheap typed decision + fallback, and existing inference router with frozen tests. Authorization and financial/effectful steps remain deterministic and human-governed even if an advisory model predicts ALLOW.
5. **GPU-to-agent budget:** trace one permitted task with exact model adapter/tokenizer/hardware revision and receipts through inference caching, quantization and serving. Compare task success, latency, energy status and true billable cost; not screenshots or estimated savings.

## Publication and independence

Canonical source is GitHub, HF is a separately checked deployment target. Each change needs owner-head reconciliation, source CI, a clean wheel/container, approved review, protected-main merge and live consumer readback. The current source work does not certify a deployed Space or the whole SZL organization. Keep partial, unknown and unavailable evidence visible.
