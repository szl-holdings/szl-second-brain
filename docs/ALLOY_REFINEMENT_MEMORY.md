# Alloy Refinement Memory

Second Brain stores only aggregate, content-addressed repair-pattern handles from
validated `szl.refinement.receipt/v1` records.

## Public state

`data/refinement-patterns.public.json` uses
`szl.second-brain.refinement-memory/v1` and exposes:

- receipt and pattern counts;
- `error_code × model_pair_sha256` handles;
- repair attempts and verified repair rate;
- regression rate;
- mean audit confidence;
- a state SHA-256;
- explicit `NONE` authority for training, promotion, execution, and merge.

It does not contain task text, gold answers, public-step summaries, provider
prompts, raw completions, hidden reasoning, credentials, or private graph nodes.
The validator rejects those fields recursively before aggregation.

## Runtime

The Docker entrypoint imports `app_refinement:app`, which extends the existing
operational Second Brain app with:

```text
GET /api/v1/refinement-memory?error_code=ARITHMETIC_ERROR&limit=50
```

There is deliberately no public receipt-ingestion route. A future ingestion job
must run through protected source, validate immutable receipt identity, produce a
reviewed public projection, and then publish through the canonical GitHub-owned
writer.

Pattern frequency is not correctness proof. All handles remain
`REVIEW_REQUIRED` and are suitable only for retrieval, qualification planning,
and read-only Anatomy observability.
