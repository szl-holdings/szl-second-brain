# Public NeoMME cache: measured-performance follow-through

The 1.4.0 native exercise actually indexed all 575 public chunks and completed
all eight diagnostic queries with body reranking and authorized hydration parity.
It exposed a real performance problem: per-query CPU times of approximately
12.9 to 49.5 seconds for a 24-candidate body rerank. The first-process index build
was 396.55 seconds. These are observations from HF job
https://huggingface.co/jobs/SZLHOLDINGS/6a9ff40cb012ba1d5b8f2af5 at exact source
`1db2ad1f8db869cbc4c847d8cd595318af283243`, not a relevance benchmark or SLA.
The first complete report digest was
`9f921747a9a87e3811e2ed19b524d50dc4592452de78df856be3735870ea68f4`.
A completed first process does not establish the full job's restart check passed.

This patch retains the already-computed public document token embeddings instead
of throwing them away after dense indexing and re-encoding the same bodies on
every query. A 256 MiB default LRU budget (configurable from zero to 512 MiB)
counts tensor payload bytes, NOT total Python/process/active-request memory.
Keys bind exact corpus, model/runtime identity, node ID, body digest and title
digest. Query embeddings and private memory are not retained in this cache.

Body lookups remain behind the existing exact-public-corpus and candidate
source/digest checks. A changed encoder identity fails closed and requires a
separately admitted generation; it never relabels an existing dense index or
reuses another model's token cache. Invalid limits, oversized entries and LRU
accounting are covered by explicit unit tests.

The persisted dense index format is unchanged and still requires an externally
supplied checksum on restore. The token cache is deliberately in-process: after
a fresh process restore, body lookups warm it lazily and have different latency
from a fully warm index. Neither this cache nor JSON index persistence is a
private memory/revocation store or a multi-replica durability claim.

The actual corpus probe now reports stage/count progress and cache observations
per query. Compare complete runs of the same eight predeclared queries, candidate
budget, model, source and index identities. Unit tests using fake payloads prove
cache contracts only. New performance improvement and full cold-restore claims
remain unmeasured until the new native run is complete. Do not mark the existing
Forge/HF inference service as upgraded solely because this patch merged.
