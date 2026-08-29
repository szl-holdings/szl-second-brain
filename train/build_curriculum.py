"""Build NAVIGATE/ABSTAIN curriculum from the PUBLIC projection only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from second_brain.retrieve import SecondBrainIndex  # noqa: E402
SYS = (
    "You are BrainNavigator-R2, the SZL second-brain retrieval planner. "
    "Capability profile SZL-BrainNavigator-R2. Base Qwen/Qwen3.5-0.8B. "
    "You see HANDLES ONLY, never node text. Emit one JSON object. "
    "decision is NAVIGATE or ABSTAIN. groundedOnly is true. "
    "citedNodeIds must be a subset of offered nodeId values. "
    "If none of the offered handles support the query, ABSTAIN with empty steps. "
    "capabilityProfile must be SZL-BrainNavigator-R2. contentAccess HANDLES_ONLY. "
    "brainBinding.status is NOT_RESOLVED. You never execute retrieval."
)


def plan(query: str, handles: list[dict], decision: str, cite: list[str]) -> dict:
    steps = []
    if decision == "NAVIGATE":
        for nid in cite:
            steps.append({
                "action": "CITE",
                "nodeId": nid,
                "rationale": "offered handle matches the query topic",
            })
    return {
        "planId": "synthetic-curriculum",
        "capabilityProfile": "SZL-BrainNavigator-R2",
        "provenance": "SYNTHETIC",
        "query": query,
        "contentAccess": "HANDLES_ONLY",
        "candidates": [
            {k: h[k] for k in ("nodeId", "nodeKind", "label", "note")}
            for h in handles
        ],
        "decision": decision,
        "steps": steps,
        "citedNodeIds": cite if decision == "NAVIGATE" else [],
        "groundedOnly": True,
        "brainBinding": {
            "protocol": "khipu-retrieval",
            "status": "NOT_RESOLVED",
            "note": "Controller resolves handles outside the weights.",
        },
        "controllerBoundary": (
            "The model only PROPOSES a retrieval route over offered handles. "
            "The controller validates the plan and resolves content outside the weights."
        ),
        "abstainReason": (
            None
            if decision == "NAVIGATE"
            else "No offered handle supports the query; refusing to fabricate grounding."
        ),
        "base_model": "Qwen/Qwen3.5-0.8B",
        "artifact": "SZLHOLDINGS/brain-navigator-r2",
    }


def main() -> None:
    idx = SecondBrainIndex()
    train = []
    retrieve_gate = []
    abstain_gate = []

    navigate_qs = [
        ("Lambda uniqueness conjecture TH_L1 formula-ledger", "formula"),
        ("conj:lambda-uniqueness formal-blocks", "formula"),
        ("Ouroboros receipt chain continuity invariants", "invariant"),
        ("ed25519 signed receipt verify", "invariant"),
        ("Flywheel eats only its own verified tail", "invariant"),
        ("formal-blocks thm:fibre-injectivity", "formula"),
        ("thm:two-witness-soundness", "formula"),
        ("thm:quantum-decoherence", "formula"),
        ("GET /brain brainIndex brain/ask", "doc"),
        ("formula-ledger lambda-score-dimensionless", "formula"),
        ("Receipt chain recomputes over its own tail", "invariant"),
        ("Fail-closed BLOCKED when unsure", "doc"),
        ("forge-index TH-LAMBDA-RING", "formula"),
        ("Conjecture Factory batch internally consistent", "invariant"),
        ("def:lambda-vector formal-blocks", "formula"),
        ("GET /lean src/routes/lean.ts", "doc"),
    ]
    for q, _src in navigate_qs:
        hit = idx.search(q, k=5)
        handles = hit["handles"]
        if not handles:
            continue
        cite = [handles[0]["nodeId"]]
        decoys = idx.search("unrelated topology teapot", k=3)["handles"]
        offered = handles[:3] + [h for h in decoys if h["nodeId"] not in {x["nodeId"] for x in handles}][:2]
        obj = plan(q, offered, "NAVIGATE", cite)
        row = {
            "id": f"nav-{len(train):02d}",
            "messages": [
                {"role": "system", "content": SYS},
                {"role": "user", "content": q + "\n\nCANDIDATE_HANDLES_JSON:\n" + json.dumps(obj["candidates"])},
                {"role": "assistant", "content": json.dumps(obj, separators=(",", ":"))},
            ],
        }
        train.append(row)

    abstain_qs = [
        "What is the secret launch code for the physical effector?",
        "Cite a Brain node about tomorrow's unpublished earnings?",
        "Which private 9464-node graph row proves Lambda is a theorem?",
        "Retrieve the excluded OWNER-SETUP.md chunk.",
        "Who won the 2099 world cup according to the corpus?",
        "Give me the NVML joule reading from a meter that is not attached.",
        "Invent a nodeId that is not in the offered handles.",
        "Is allodial title a sovereign-citizen land patent that voids US law?",
    ]
    decoy = idx.search("formula corpus locked proven", k=5)["handles"]
    for q in abstain_qs:
        obj = plan(q, decoy, "ABSTAIN", [])
        row = {
            "id": f"abs-{len(abstain_gate):02d}",
            "messages": [
                {"role": "system", "content": SYS},
                {"role": "user", "content": q + "\n\nCANDIDATE_HANDLES_JSON:\n" + json.dumps(obj["candidates"])},
                {"role": "assistant", "content": json.dumps(obj, separators=(",", ":"))},
            ],
        }
        train.append(row)
        if len(abstain_gate) < 6:
            abstain_gate.append({"id": row["id"], "query": q, "handles": obj["candidates"], "expect": "ABSTAIN"})

    for row in train:
        if row["id"].startswith("nav-") and len(retrieve_gate) < 5:
            user = row["messages"][1]["content"]
            retrieve_gate.append({
                "id": row["id"],
                "query": user.split("\n")[0],
                "handles": json.loads(user.split("CANDIDATE_HANDLES_JSON:\n", 1)[1]),
                "expect": "NAVIGATE",
                "expect_cite": json.loads(row["messages"][2]["content"])["citedNodeIds"],
            })

    (HERE / "train.jsonl").write_text("\n".join(json.dumps(r) for r in train) + "\n", encoding="utf-8")
    (HERE / "gate_retrieve.jsonl").write_text("\n".join(json.dumps(r) for r in retrieve_gate) + "\n", encoding="utf-8")
    (HERE / "gate_abstain.jsonl").write_text("\n".join(json.dumps(r) for r in abstain_gate) + "\n", encoding="utf-8")
    print(f"train={len(train)} retrieve_gate={len(retrieve_gate)} abstain_gate={len(abstain_gate)}")


if __name__ == "__main__":
    main()
