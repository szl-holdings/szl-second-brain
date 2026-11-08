---
name: szl-sweep
description: >
  Trigger phrase: "szl holdings sweep" (also "szl sweep", "estate sweep").
  Invokes the embedded governed-sweep payload: runs the estate confabulation
  battery or a governed training/audit sweep through the launch contract, and
  reads back a khipu receipt - never prose without provenance.
license: apache-2.0
---

# szl-sweep — the estate's invocable command grammar

## When this skill activates

Any of these trigger phrases, from a human or an agent (MCP client, Claude,
estate model):

- `szl holdings sweep`
- `szl sweep`
- `estate sweep <target>`

## What it does

1. **Parse** the trigger into `(action, target)` — e.g. `szl sweep battery`,
   `szl sweep alignment`, `szl sweep train <wave-name>`.
2. **Load the embedded payload** — pure Python, in this skill directory, one
   payload per action. Payloads are versioned with the repo; the trigger never
   fetches remote code.
3. **Execute through the gates** — training/eval actions route through the
   szl-forge launch contract (immutable pins, disjoint holdout, admission);
   read-only actions are bounded and read-only.
4. **Read back a receipt** — the payload's output is a khipu receipt
   (szl.receipt/v1 JSON: schema, action, inputs, outputs, hashes, verdict,
   FAIL preserved verbatim). The readback is the receipt, not a summary.

## The grammar

    szl sweep battery            -> run the 6-probe confabulation battery on a target model
    szl sweep battery <model-id> -> same, on the named model (pinned revision required)
    szl sweep alignment          -> regenerate + verify the estate alignment manifest
    szl sweep receipts           -> list/verify recent khipu receipts
    szl sweep train <wave>       -> launch a governed training wave (requires the launch contract)

## Doctrine

A trigger phrase is a pointer into a governed capability. The phrase alone
never authorizes a mutation: training and Hub writes still require the launch
contract's gates. The readback always carries provenance. Failures stay
published.
