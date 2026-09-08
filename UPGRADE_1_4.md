# Second Brain 1.4: executable public neural integration

This release changes the existing index and hybrid coordinator, not just a plan.
It does not assert that an existing Forge deployment has upgraded its pinned wheel.

## What changes

Whole-corpus admission now rejects malformed rows, missing/wrong text digests,
duplicate IDs/JSON keys and non-finite JSON. Explicit expected file digests also
bind titles, source identities and order. A reload stages all rows, then swaps
one immutable generation. Rejected candidates leave the prior generation active
and expose `ACTIVE_PREVIOUS_RELOAD_REJECTED`. This is in-process generation
consistency, not a complete durable tenant lifecycle or deletion system.

`search_candidates(limit=...)` supplies up to 128 internal candidates. Public
search/context remain capped at 12. The coordinator uses the larger recall pool
and captures one immutable generation for each request. Existing BM25-like scores
and corpus-order sparse tie breaks are preserved; a full BM25 algorithm change
is not smuggled into this release.

Invalid dense/reranker output, source drift and authorization errors propagate;
only explicit `ProviderUnavailable` can use the configured fallback. Adapters
must classify actual service outages deliberately. Legacy generic RuntimeError
is no longer assumed safe to suppress. Empty/malformed reranker output cannot
produce a success label. Authorizers must return actual True, not truthy strings.

## Real opt-in public neural provider

`second_brain.neomme.NeoMME` loads the exact Hcompany checkpoint from a fully
materialized, verified local directory. It uses native Transformers classes,
`local_files_only=True`, `trust_remote_code=False`, safetensors, CPU float32,
and an explicit input-token budget. It never downloads on import or query.
The packaged `data/neomme-260m.lock.json` includes all eight artifact hashes.
Hcompany retains model authorship and Apache-2.0 notices.

`PublicNeuralBrain` rejects any corpus other than the exact 575-row packaged
public projection. It computes real dense vectors, persists/restores them with
an externally supplied file digest, injects a dense provider into the EXISTING
HybridSecondBrain, and reranks using authorized public body text and MeanMaxSim.
Public results remain handles/digests. Model, runtime, index and corpus bindings
are included in the ranking receipt. The base package does not import Torch.

```python
from pathlib import Path
from second_brain.neomme import NeoMME, PublicNeuralBrain

encoder = NeoMME(Path('/protected/materialized-neomme'))
brain = PublicNeuralBrain(encoder)
# Explicit evaluation/staging, not production activation:
index_sha = brain.build(Path('/protected/staged-public-index.json'))
# On a fresh process, get the expected digest from the admitted controller config:
brain.load(Path('/protected/staged-public-index.json'), expected_sha256=index_sha)
context = brain.coordinator(rerank=True).context('Lambda uniqueness conjecture', k=6)
```

The full-corpus exercise in `tools/neomme_corpus_probe.py` is an execution,
persistence and hydration test, NOT an independent relevance benchmark. It uses
predeclared diagnostic queries and preserves baseline/candidate ranks without
claiming which is better. The existing eight-query toy smoke is not promoted
into a 575-query evaluation.

## Remaining closure

Forge must qualify the worker and independent Brain qrels comparison, retain an
admitted index digest, update its exact package/controller/image locks, inject the
provider, and verify the actual public runtime before any live capability claim.
No opaque dependency is auto-enabled by a package upgrade. Private-source
binding, pre-ranking ACLs/revocation epochs, private-session import, durable
multi-replica activation/purge, audio and document-image lanes remain separate
unfinished portions of Payload 1. This public-only module is not a substitute.

Deployment remains GitHub -> Hugging Face -> a-11-oy.com -> a11oy.net. No second
public Brain Space, new model mirror, training run or private graph publication
is introduced. No safety/quality superiority, certification or SLA is claimed.
