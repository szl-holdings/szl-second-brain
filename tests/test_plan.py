from second_brain.plan import plan_from_handles
from second_brain.retrieve import SecondBrainIndex


def test_navigate_cites_offered_handle() -> None:
    idx = SecondBrainIndex()
    hit = idx.search("Lambda uniqueness conjecture TH_L1", k=5)
    plan = plan_from_handles("Lambda uniqueness conjecture TH_L1", hit["handles"])
    assert plan["decision"] == "NAVIGATE"
    assert plan["citedNodeIds"]
    offered = {h["nodeId"] for h in hit["handles"]}
    assert set(plan["citedNodeIds"]) <= offered
    assert plan["contentAccess"] == "HANDLES_ONLY"
    assert plan["brainBinding"]["status"] == "NOT_RESOLVED"
    assert plan["raw_graph_nodes_admitted_to_gradients"] == 0


def test_abstain_on_unsupported_query() -> None:
    decoys = [
        {
            "nodeId": "pub-formula-001",
            "nodeKind": "INDEX",
            "label": "DECLARED",
            "note": "formula corpus locked proven",
        }
    ]
    plan = plan_from_handles(
        "Who won the 2099 world cup according to the corpus?", decoys
    )
    assert plan["decision"] == "ABSTAIN"
    assert plan["citedNodeIds"] == []
    assert plan["steps"] == []
    assert plan["abstainReason"]
