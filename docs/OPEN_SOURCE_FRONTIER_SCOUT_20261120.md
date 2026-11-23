# Open-source frontier scout: source-pinned adoption candidates (pass 1)

**Observation:** 2026-11-20 UTC. **Scope:** public-source research only; no upstream code imported, model inference, paid service, provider configuration, deployment, training, or automatic source promotion. **Disposition:** REVIEW REQUIRED. The phrase "make it ours" means build SZL-owned integrations and differentiated behavior while respecting each upstream license, attribution, trademarks, and data-use rights; never re-label third-party code, weights, datasets, or results as SZL-original.

## Source-of-truth and what is already implemented

These are the GitHub protected-main commits observed through a read-only public GitHub branch API on BETTERWITHAGE for this survey. They are source identities, not deployment identities:

| SZL owner | Source SHA | Existing boundary |
| --- | --- | --- |
| [szl-second-brain](https://github.com/szl-holdings/szl-second-brain) | `1736afff14ff3fd2202b701873cc01a719462dae` | 575 public governed chunks; handles-only public memory, controller-only hydration, review-gated frontier memory, lexical hybrid retrieval, unsigned evidence receipts |
| [anatomy](https://github.com/szl-holdings/anatomy) | `0ca96e524ee9c7ff15e13eee40feeb56ae9e4476` | Three.js visualization and evidence feeds; source/feed state and browser renderer state must be independent |
| [a11oy](https://github.com/szl-holdings/a11oy) | `6a6f9df5417f84b4512152cead63f2b46c2b482c` | canonical governed product, signed turn and runtime admission owner |
| [szl-router](https://github.com/szl-holdings/szl-router) | `84a980a71bc775a75afbca16865ad1e200b6dd1e` | default-deny, model-digest-qualified routing; hosted inference is a separate approval |
| [holographic-unify](https://github.com/szl-holdings/holographic-unify) | `600020978d98355157713dfa4c68d263479791dd` | simulation/hologram; not real serving or Khipu weights |
| [szl-sovereign-os](https://github.com/szl-holdings/szl-sovereign-os) | `b0ddb97b13608be232a18896b24684d11a68f6ef` | folded/retired standalone publication, historical source only; do not rehost |

**Avoid duplication:** Second Brain already has [integration research](https://github.com/szl-holdings/szl-second-brain/blob/1736afff14ff3fd2202b701873cc01a719462dae/docs/INTEGRATION_RESEARCH_20261101.md) covering FastAPI, GraphRAG, HiRAG, LangGraph, NeMo Guardrails and RRF. It already has [ecosystem research](https://github.com/szl-holdings/szl-second-brain/blob/1736afff14ff3fd2202b701873cc01a719462dae/docs/EVIDENCE_ECOSYSTEM_20261116.md) covering optional LangChain/LangGraph/NVIDIA Relay integration, Palantir-inspired typed evidence, and a proposed counterfactual-evidence-loss experiment. The existing hourly source refresh uses an allowlisted research corpus and a rights-gated, content-addressed review workflow. This pass adds upstream candidate analysis and test design; it does not create a second execution controller or unrestricted web-scraping pipeline.

The **active P0** remains [a11oy #3776](https://github.com/szl-holdings/a11oy/issues/3776): Khipu expected exact tag and served model/artifact identity are not yet qualified. An HTTP 200 Second Brain snapshot, HF RUNNING control Space, or healthy Three.js feed cannot prove signed inference. Do **not** camouflage this incident with a new retrieval engine.

## Public open-source shortlist: exact pinned revisions

Licenses below are repository-level observations at survey time, not a legal opinion or an audit of transitive dependencies, assets, pretrained weights, datasets, or managed-cloud terms. Before copying or vendoring, review the exact file's notices, dependency SBOM, policy and allowed data flows at the pin.

| Upstream, exact observed SHA | Repo license/readback | Useful idea | SZL decision and constraint |
| --- | --- | --- | --- |
| [getzep/graphiti@9b8a463](https://github.com/getzep/graphiti/tree/9b8a4630092084734b080f2e6f409c2c23bdcc3a) | Apache-2.0 | Time-valid facts, episodes, supersession, temporal queries, provenance | **P1, prototype contract, not install-by-default.** Add bitemporal handle metadata to independently versioned evidence; never leak private episodes into public projection or silently replace review gates. Graphiti's optional backends and LLM calls need separate budget/privacy review. |
| [mem0ai/mem0@fff8a647](https://github.com/mem0ai/mem0/tree/fff8a6472512d1bc1a4bccab8c645b65a1df7fe5) | Apache-2.0 OSS SDK | Memory extraction/search interface and temporal prioritization | **P1, compare interfaces only.** Mem0 reports managed-platform improvements which are *not* guaranteed by its open-source SDK; do not adopt vendor performance claims as SZL benchmarks. No memory writes without source and tenant rights. |
| [microsoft/graphrag@34b2b67](https://github.com/microsoft/graphrag/tree/34b2b67ae4601ad0b47bcd179fbe3f2a23aa0857) | MIT | Local/global query routing, community-oriented retrieval, explicit indexing and generation costs | **Existing study; benchmark design only.** Upstream README reports largely maintenance mode; high graph indexing/model-call costs, additional generation gates. Do not duplicate the previous integration review. |
| [letta-ai/letta@8816d3a](https://github.com/letta-ai/letta/tree/8816d3a8516893bfdc0fa14bfb1235226012e295) | Apache-2.0 historical repository | Persistent agent memory and checkpoints | **Watch, not ingest.** Current Letta runtime moved to `letta-ai/letta-code`; independently pin and inspect that repository before any adoption. Its license excludes brand assets. Durable agent state is not authorization to mutate memory, code or the provider. |
| [pgvector/pgvector@b8b2b6e](https://github.com/pgvector/pgvector/tree/b8b2b6ed9951997c7e846bfd3a04a05f81e52009) | PostgreSQL-style LICENSE; GitHub SPDX metadata returned `NOASSERTION` | Versioned, transactionally managed vectors with tenant filters | **P2 optional backend feasibility.** License-review the exact terms; stage tests on a local public fixture only, no DB migration or private corpus indexing. |
| [mrdoob/three.js@8b92052](https://github.com/mrdoob/three.js/tree/8b92052852735b67cfa8393f78e707b3f07a0eec) | MIT | WebGL/WebGPU scene engine and rendering | **P1 reuse existing Anatomy stack.** Browser E2E on WebGL enabled, disabled, context loss and missing feed. Preserve keyboard/accessible HTML fallback. Do not replace frontend solely because a new framework exists. |
| [vllm-project/vllm@6f022f1](https://github.com/vllm-project/vllm/tree/6f022f1080b78e7f5f752bfae85a95cf819a402c) | Apache-2.0 | Efficient paged KV cache, batched GPU serving | **P2 bench candidate only** after exact model/weights/hardware, license, auth and signed-turn gates qualify. No model boot or live GPU experiments in this pass. |
| [sgl-project/sglang@08f1009](https://github.com/sgl-project/sglang/tree/08f10090c76294a458c7b307e1ba97bd7ff1654e) | Apache-2.0 | Alternative high-performance LLM/VLM serving | **P2 head-to-head candidate** under identical workload and receipts; no unreviewed change to provider identity or ingress. |
| [ggml-org/llama.cpp@b94959a](https://github.com/ggml-org/llama.cpp/tree/b94959a64d011915d77a5381c7d4846dcda99530) | MIT | Local CPU/GPU quantized inference and GGUF | **P2 baseline candidate.** Pin GGUF/model-card license, immutable weight digest and architecture support separately from server code. |
| [sigstore/cosign@339a3ca](https://github.com/sigstore/cosign/tree/339a3ca85413b4d89a49daf1eb554591c93ee365) | Apache-2.0 | Keyless artifact signatures, verified in-toto/DSSE attestations | **P0 reference for verifier design, not blanket green.** Verify trusted signer identity, issuer, immutable artifact digest, timestamp/freshness, and per-turn binding. Existing SZL structural hashes and unsigned receipts must stay labeled unsigned. |

Other candidate classes for *later* passes: NVIDIA NeMo Relay (existing adapter), OpenTelemetry semantic-convention instrumentation, in-toto/SLSA provenance, immutable vector indexing, formally checked runtime invariants, browser accessibility/visual regression, model serving, data rights and supply-chain scanners. A broad public-source sweep does **not** confer permission to harvest copyrighted full text or model outputs for training.

## Research papers and a differentiating SZL hypothesis

- [MemDream (arXiv:2609.34545)](https://arxiv.org/abs/2609.34545): proposes proactively probing memories with a dreamer/analyst/consolidator cycle. *Paper hypothesis; no executable code or reuse license was established in this survey*. Research direction only; any performance figures belong to the authors and are not transferable to SZL.
- [MRAgent (arXiv:2606.06036)](https://arxiv.org/abs/2606.06036): dynamic associative retrieval instead of a fixed retrieve-then-reason path. **Research-only** until paired reproducibility and rights checks.
- [LifelongAgentBench (arXiv:2505.11942)](https://arxiv.org/abs/2505.11942): evaluate retained knowledge and transfer under interactive tasks. Use its concepts for a *separate* rights-cleared fixture; do not ingest benchmark answers into training.

**Candidate original SZL experiment — proof-carrying temporal memory with counterfactual abstention:**

1. Each public fact handle preserves source repo/path/immutable revision, observation timestamp, claimed effective-time interval, licensing/rights state, content digest, and supersession dependency; preserve a distinct private hydration boundary.
2. A bounded, deterministic **challenger** generates offline test cases from already admitted *public* handle metadata (not provider prompts or private full text): stale source, contradictory revisions, missing evidence, source withdrawal, malformed receipts, unknown license, and false-positive readiness.
3. A read-only **analyst** computes lost-evidence impact and expected abstention; an optional separately approved inference judge may be added later but never decides source authority.
4. The **consolidator** proposes a candidate artifact/PR with an exact diff, source pins, license obligations, diagnostics, and counters. It cannot write directly to admitted memory, training, GPU provider state, production or locked Lean claims.
5. The accepted output is an evidence-carrying query decision; *cryptographic attestation* is claimed only if the actual independent signature verification succeeded. Typed semantics and Lean witnesses must retain their exact scope.

This is an unproven, testable engineering proposal, not a novelty or performance claim. It adds a time- and rights-aware abstention gate on top of existing SZL public handles and the prior counterfactual-loss proposal; the substantive novelty question requires literature review and controlled comparison.

## Pre-registered experiment and acceptance

Use a fixed, independently reviewed **public and rights-cleared** corpus and held-out question bank. Stratify entity lookup, time-validity/supersession, multi-source evidence, contradictions, deliberately unanswerable prompts, missing-source failures, and source-retraction/expiry cases. Compare the current lexical/RRF baseline against (A) typed temporal validity filter, (B) optional qualified dense rerank, and (C) ablated counterfactual abstention. Change **one component at a time**, with paired queries and seed/version locks.

Record `Recall@k`, `nDCG@k`, citation/source-binding validity, answer unsupported-claim rate (only after a separately qualified model), false and correct abstention, stale-fact leakage, tenant-boundary violations, p50/p95 latency, memory/VRAM, index construction time, token/billing cost and explicit denominators. No success is declared if negative security tests, rights checks or source binding regress, even if ranking improves. Report uncertainty estimates and failures, not only averages.

Minimum local unit acceptance, before *any* production wiring:

- Duplicate source IDs, malformed/extra fields, timestamp conflicts, changed digests and expired observations **fail closed**.
- No private material or non-admitted research candidate appears in public handles, graph exports, browser tooltips or logs.
- License unknown/restricted => **REVIEW_REQUIRED**, never copied into weights or product.
- A source feed HTTP 200 cannot green-light a broken WebGL renderer; WebGL failure cannot falsely mark all source feeds DOWN.
- Router `/readyz/inference` 503 means inference not configured; HTTP 200 alone never proves signed, source-matched, real-model execution.
- An empty test denominator => **UNAVAILABLE**, not 100%. Generated claims must be tied to offered handles and independent receipts.
- Any adapter remains optional and removable; no extra standing scheduler, signing secret, paid provider call or unmanaged network egress.

## Team execution lanes and the next nine **unperformed** passes

| Pass | Owning lane | Objective / tangible artifact | Gate |
| --- | --- | --- | --- |
| **1 DONE: source scouting** | Research / Second Brain | This pinned public shortlist and experiment spec | **REVIEW REQUIRED** |
| 2 | Memory researcher | Evaluate Graphiti/Mem0 temporal schema, licensing, transitive dependencies, data boundaries | Public synthetic contract tests |
| 3 | Retrieval engineer | Run rights-cleared baseline, temporal, dense ablation and abstention tests | Held-out scorecard with cost/uncertainty |
| 4 | Inference owner | Validate exact on-host provider architecture under existing router and [A11oy #3776](https://github.com/szl-holdings/a11oy/issues/3776) | Operator approval before any model generation/spend |
| 5 | Cryptographic verifier | Audit receipt identity, signing, time, provenance and negative cases | Independent replay of genuine signed turns |
| 6 | Anatomy/browser engineer | Browser 3D vs feed vs fallback E2E, renderer context loss | Real browser evidence, exact deployed source |
| 7 | Security engineer | SBOM, licensing, provenance, privacy, data rights, cache/egress/secret hygiene | No high-severity unowned exposure |
| 8 | Performance engineer | Offline comparator across available engines after provider qualification | Equal weights/hardware/workloads, real energy meter or UNAVAILABLE |
| 9 | Platform release owner | Source → HF immutable artifact → Cloudflare protected product alignment | Protected checks/reviews, publisher verification |
| 10 | Independent challenger | Repeat negative tests, drift probes, source-chain parity and restore exercise | Reviewed complete evidence; no auto-promotion |

**Cadence:** run one bounded pass at a time against current protected main; retain exact source pins and evidence in reviewed GitHub artifacts. The table is an execution queue, **not** a claim that passes 2–10 or Kimi/Mistral co-review occurred. The presence of `kimi-estate-ops:latest`, `mistral-nemo:12b` and `khipu:latest` in BETTERWITHAGE Ollama metadata is local inventory only, not permission to invoke them, to publish their ports, or evidence that cloud inference is configured.

**Owner repair priority:** A11oy/router owner first resolves #3776 with authorized HTTPS ingress, verified exact Khipu model/weight bytes, independently verified signed turn and separate production admission; Second Brain owner stages the temporal/abstention experiment on public handles; Anatomy owner proves browser rendering separately. No protection bypass, credential exposure, bulk unrestricted crawling, model generation, provider configuration, cloud cost, production deployment or rights gate change was performed in this scout.
