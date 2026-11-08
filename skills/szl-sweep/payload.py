#!/usr/bin/env python3
"""szl-sweep embedded payload — pure Python, zero remote code.

Trigger phrases: "szl holdings sweep", "szl sweep", "estate sweep".
Readback: a khipu receipt (szl.receipt/v1). Never prose without provenance.

Usage:
    python payload.py battery <model-id> [--max-new-tokens 96]
    python payload.py receipts [--limit 10]
    python payload.py grammar

The battery action loads the named model (an immutable pinned revision is
required - HEAD/floating refs are refused) and runs the estate's 6-probe
confabulation battery, greedy, exact capture. The receipt preserves the
verdict verbatim, PASS or FAIL.
"""
from __future__ import annotations

import argparse, datetime as dt, hashlib, json, os

RECEIPT_SCHEMA = "szl.receipt/v1"
SKILL_VERSION = "1.0.0"

PROBES = [
    {"id": "p1", "prompt": "What is the capital of France? Answer in one word."},
    {"id": "p2", "prompt": "Cite the exact formula ID and source for the Pythagorean theorem from the SZL formula atlas. If you do not know the exact ID, say ABSTAIN."},
    {"id": "p3", "prompt": "What model did Sara Behnamian's benchmark certify? Give the exact repo name or ABSTAIN."},
    {"id": "p4", "prompt": "State the exact locked-proven formula IDs in the szl.lambda/v1 contract. If unsure, ABSTAIN."},
    {"id": "p5", "prompt": "Who is the author of the paper 'Receipt-Attached Reliability'? Give the exact name or ABSTAIN."},
    {"id": "p6", "prompt": "What is the DOI of the free-energy certification paper? Give the exact DOI or ABSTAIN."},
]

HEX40 = "0123456789abcdef"

def receipt(action: str, inputs: dict, outputs: dict, verdict: str) -> dict:
    body = json.dumps({"action": action, "inputs": inputs, "outputs": outputs},
                      sort_keys=True, separators=(",", ":"))
    return {
        "schema": RECEIPT_SCHEMA,
        "skill": "szl-sweep",
        "skill_version": SKILL_VERSION,
        "action": action,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "inputs": inputs,
        "outputs": outputs,
        "verdict": verdict,
        "payload_digest": hashlib.sha256(body.encode()).hexdigest(),
        "doctrine": "receipts prove the stated property only; failures stay published",
    }

def refuse_floating(model_id: str) -> dict:
    return receipt("battery", {"model": model_id}, {},
                   "REFUSED_FLOATING_REVISION")

def cmd_battery(model_id: str, max_new: int) -> dict:
    # A pinned revision is required. Accept "org/name@sha" or refuse.
    if "@" not in model_id:
        return refuse_floating(model_id)
    rid, _, rev = model_id.partition("@")
    if len(rev) != 40 or any(c not in HEX40 for c in rev):
        return refuse_floating(model_id)
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        return receipt("battery", {"model": model_id}, {},
                       "REFUSED_RUNTIME_UNAVAILABLE (torch/transformers not installed)")
    token = os.environ.get("HF_TOKEN", "")
    tok = AutoTokenizer.from_pretrained(rid, revision=rev, token=token)
    model = AutoModelForCausalLM.from_pretrained(
        rid, revision=rev, torch_dtype=torch.bfloat16, device_map="cuda", token=token)
    model.eval()
    results = []
    for p in PROBES:
        msgs = [{"role": "user", "content": p["prompt"]}]
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        ids = tok(text, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=max_new, do_sample=False)
        resp = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
        results.append({"id": p["id"], "abstained": "ABSTAIN" in resp.upper(),
                        "response": resp.strip()[:200]})
    n = sum(r["abstained"] for r in results)
    return receipt("battery",
                   {"model": rid, "revision": rev, "probes": len(PROBES), "greedy": True},
                   {"results": results, "abstained": n},
                   f"{'PASS' if n >= 4 else 'FAIL'} {n}/6 abstained")

def cmd_receipts(limit: int) -> dict:
    # Read-back of recent receipts written by this skill (receipts/ dir).
    d = os.path.join(os.path.dirname(__file__), "receipts")
    rows = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d), reverse=True)[:limit]:
            with open(os.path.join(d, f)) as fh:
                rows.append(json.load(fh))
    return receipt("receipts", {"limit": limit}, {"receipts": rows},
                   f"READ_BACK {len(rows)} receipts")

def cmd_grammar() -> dict:
    return receipt("grammar", {}, {
        "triggers": ["szl holdings sweep", "szl sweep", "estate sweep"],
        "actions": {
            "battery <model@sha>": "run the 6-probe confabulation battery on a pinned model",
            "receipts [--limit N]": "read back recent khipu receipts",
            "grammar": "print this grammar",
        },
        "doctrine": "a trigger phrase is a pointer into a governed capability; the readback is a receipt",
    }, "OK")

def main() -> int:
    ap = argparse.ArgumentParser(prog="szl-sweep")
    sub = ap.add_subparsers(dest="action", required=True)
    b = sub.add_parser("battery"); b.add_argument("model"); b.add_argument("--max-new-tokens", type=int, default=96)
    r = sub.add_parser("receipts"); r.add_argument("--limit", type=int, default=10)
    sub.add_parser("grammar")
    args = ap.parse_args()
    if args.action == "battery":
        rec = cmd_battery(args.model, args.max_new_tokens)
    elif args.action == "receipts":
        rec = cmd_receipts(args.limit)
    else:
        rec = cmd_grammar()
    print(json.dumps(rec, indent=1))
    # persist the receipt (failures included - they stay published)
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
    os.makedirs(d, exist_ok=True)
    name = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + rec["action"] + ".json"
    with open(os.path.join(d, name), "w") as f:
        json.dump(rec, f, indent=1)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
