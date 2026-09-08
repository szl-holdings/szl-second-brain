# Public NeoMME cache: measured CPU evidence

The NeoMME public-corpus cache is now measured on the complete packaged public corpus rather than described only through unit-test behavior.

The authoritative observation is Hugging Face CPU job `SZLHOLDINGS/6a9ff8ff8e5f7b7fd14cbbe3`, completed on 2026-09-08. It executed candidate source `76e1eb42a115b41724fa469ba238f1d81bd13583`, which was admitted through PR #19 and protected-main merge `74aea2a4103fcf9cd6d013b69fbe51e5472f4bb6`. The installed package reported version `1.4.1`.

## Bound source and model

- Source repository: `szl-holdings/szl-second-brain`
- Model: `Hcompany/NeoMME-260M-Retriever`
- Model revision: `0dcb6c924435bd0bf5d504dba9ba2bb63acd8595`
- Model-lock SHA-256: `957e56a53a74e51ec75a679524eab07769806734caedfce9e5263521bd42f65a`
- Transformers revision: `cdfdcad31314fe4f23b40ab374e860a62403f72a`
- Runtime: PyTorch `2.8.0+cpu`, float32, L2-normalized embeddings
- Corpus scope: `EXACT_PACKAGED_PUBLIC_CORPUS_ONLY`
- Corpus SHA-256: `387337acbd8fe443637102fe7ea75387fa4c3d9d746d8ab6e2d14d6c138aad8f`

## Measured result

The job indexed all **575** public documents at **1,024** dimensions and ran all eight fixed diagnostic queries in two separate processes.

The first process built a 12,480,582-byte dense index in `388.19100568816066` seconds. Its SHA-256 was `f6c98283b5a19ea79aef468874b1ac945c2bb84351e224451dbcab91d5287ef5`. With the public-document token cache warm, median query time was `0.3286384674720466` seconds, compared with the retained uncached observation median of `42.876986605348065` seconds.

The first process cache contained 575 entries, recorded 192 hits, zero misses and zero evictions, and held 63,686,144 tensor-payload bytes under the 256 MiB cache budget. Maximum process RSS, including dependencies, was 3,639,939,072 bytes; the cache budget does not claim total-process memory control.

A fresh second process restored the exact dense index in `0.29764229292050004` seconds. Candidate rankings were identical to the first process and the earlier uncached observation, and every hydration digest matched. The in-process token cache intentionally did not persist: the fresh process lazily warmed 157 entries, recording 35 hits and 157 misses. Its eight query times ranged from approximately 12.53 to 44.73 seconds.

This distinction is deliberate: **dense-index restore is proven; cross-process token-cache persistence is not implemented or claimed.**

## Receipts

- Build receipt SHA-256: `7ad792ce9301f4bd25a3ffc01d06e1a50bba553a6519bb27bc59763c7fbdf5aa`
- Restore receipt SHA-256: `c9a7cde5bed89435d7db9cfcdcba98fe4ff09eac7d8be9a01298c8b14d0a682f`
- Receipt kind: `UNSIGNED_EXECUTION_RECORD_NOT_AUTHORIZATION`
- Machine-readable projection: `evidence/neomme-cache-1.4.1-hf-cpu-20260908.json`

## Truth boundary

This is an eight-query CPU diagnostic observation, not an independent relevance benchmark, production SLA, private-memory durability proof, model-quality winner, or deployment authorization. Training was not performed. The private graph was not loaded. Production promotion remains false.
