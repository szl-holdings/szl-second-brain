# Lutar scope challenge — development protocol, not model qualification

This offline artifact tests whether a proposed evaluator distinguishes an exact
formal scope from a broken premise, a missing premise, or an unsupported deployed
runtime claim. It preserves the canonical public Lutar source digest and does
not modify the locked-eight set, runtime admission, public retrieval corpus,
private graph, or model weights.

## Source and experimental unit

Source: `szl-holdings/lutar-lean@59d6b026b8418f59bd6535d532bdeb7551b398f0`,
`claims/locked-formulas.v1.json`, SHA-256
`5e0358ae4e0ff6345a42e8c2711c675fa4ec2366267205912892e9e46ecf5a6f`.
The retained source is Apache-2.0 public material. Exact hypotheses and refinement
limits are preserved. Scenario labels are author interpretations of those
claims; they are not newly checked Lean proof terms or independent validation.

The development split uses whole formula families, not paraphrases:

- Training-context candidates: F1, F11, F12, F19; two source-derived rows each.
- Evaluation fixtures: F4, F7, F18, F22; four variants per family.

There are eight training-context rows and sixteen evaluation cases. The existing
all-sixteen context export contains the evaluation families and is therefore
rejected by `check_training_context`. That check only controls this generated
pack: other training exposure, source-document exposure and pretraining
contamination are unknown. These public cases and expected labels cannot be
represented as a secret or blind benchmark. Create independently reviewed,
unseen evaluation families before drawing model-generalization conclusions.

## Reproduce without training or network

```sh
python experiments/lutar_scope_challenge.py --output new-plan.json
python -m pytest tests/test_lutar_scope_challenge.py
```

The exporter refuses an existing output file. The protocol records the source,
context and case digests, split unit, unrun ablation arms and explicit authority
limits. It is not included in the public Space payload and has no model loader.

`score_predictions(plan, predictions, run_binding=...)` accepts exactly one
`{case_id, label}` row for every expected case. It rejects missing, extra,
duplicate and unknown cases, undeclared fields and invalid labels. Plan and
harness identity must match the exact local implementation. Metrics include
coverage, accuracy, unsupported-claim rate, correct-abstention rate,
overabstention, per-family accuracy and paired positive/broken-premise accuracy.
Every metric retains numerator, denominator and fraction; an empty denominator
is unavailable, not a zero-percent pass. No aggregate score authorizes promotion.

## Prediction evidence

Synthetic controls identify themselves as ORACLE, ALWAYS_ACCEPT, ALWAYS_ABSTAIN
or MUTATED, with the current harness SHA-256. They report SYNTHETIC_CONTROL_ONLY.
A model-output file must also declare an immutable model repository/revision,
weight-manifest SHA-256, generation-evidence SHA-256 and decoding-config SHA-256.
These fields are required identity declarations, not independently verified run
receipts. Scoring does not run the model, verify its weights, measure latency or
energy, or establish that a submitted prediction file came from that model.
The state is PREDICTION_FILE_SCORED, never EVALUATED or QUALIFIED.

## Ablation preregistration

Compare BASELINE, SOURCE_SCOPE_CONTEXT and INDEPENDENT_PROOF_CONDITIONED with
identical base weights, optimizer/seed policy, tokenizer, compute/token budgets,
decoding, evaluator and independently held-out cases. Budget parity is currently
REQUIRED_NOT_ESTABLISHED; all arms are NOT_RUN. The proof-conditioned arm remains
blocked until an isolated worker, replayable proof store, trusted-statement
comparison and independent checker are actually verified. Do not relabel
printed axiom reports as independent checking.

Keep individual failures and original receipts. Report uncertainty over
independent theorem families rather than treating closely related variants as
independent observations. This small development suite has no claim of adequate
statistical power, superiority to a baseline, training speedup or novelty.
