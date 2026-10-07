"""Frozen software regression evaluation; failed outputs stay in denominators."""
from __future__ import annotations

from collections import defaultdict

from second_brain.corpus import strict_json

from .engine import MAX_HOPS, SCHEMA, Showcase, parse, read_fixture

RESULT_KEYS = {"schema", "synthetic", "query", "state", "reason", "answer",
               "retrieved_ids", "citations", "steps", "fixture_revision", "authority"}
CITATION_KEYS = {"record_id", "source_id", "date", "source_family", "text_sha256",
                 "fixture_revision", "quote"}
STEP_KEYS = {"subject", "predicate", "object", "record_id"}
ABSTAIN_REASONS = {"UNSUPPORTED_QUERY", "UNKNOWN_FACT", "CONFLICTING_EVIDENCE",
                   "EVIDENCE_NOT_RETRIEVED", "NO_SUPPORTED_PATH"}


def schema_valid(value: object, query: str, revision: str) -> bool:
    if not isinstance(value, dict) or set(value) != RESULT_KEYS:
        return False
    if (value["schema"] != SCHEMA or value["synthetic"] is not True
            or value["query"] != query or value["fixture_revision"] != revision
            or value["authority"] != "NONE" or not isinstance(value["reason"], str)):
        return False
    ids, citations, steps = (value[k] for k in ("retrieved_ids", "citations", "steps"))
    if not isinstance(ids, list) or len(ids) > 12 or any(not isinstance(x, str) for x in ids):
        return False
    if len(set(ids)) != len(ids):
        return False
    if not isinstance(citations, list) or not isinstance(steps, list):
        return False
    if len(citations) > MAX_HOPS or len(steps) > MAX_HOPS:
        return False
    for items, keys in ((citations, CITATION_KEYS), (steps, STEP_KEYS)):
        if any(not isinstance(x, dict) or set(x) != keys
               or any(not isinstance(v, str) or not v for v in x.values()) for x in items):
            return False
    if value["state"] == "ABSTAIN":
        return (value["reason"] in ABSTAIN_REASONS and value["answer"] is None
                and not citations and not steps)
    if value["state"] != "ANSWERED" or not isinstance(value["answer"], str) or not value["answer"]:
        return False
    if value["reason"] == "SUPPORTED_FACT":
        return len(citations) == 1 and not steps
    if value["reason"] == "SUPPORTED_PATH":
        return bool(steps) and len(citations) == len(steps)
    return False


def evidence_valid(value: dict, demo: Showcase) -> bool:
    if any(node not in demo.by_id for node in value["retrieved_ids"]):
        return False
    for citation in value["citations"]:
        row = demo.by_id.get(citation["record_id"])
        if row is None or not any(citation == demo.citation(row, c) for c in row.claims):
            return False
    for step, citation in zip(value["steps"], value["citations"]):
        row = demo.by_id.get(step["record_id"])
        if row is None or citation["record_id"] != row.id or not any(
            c.kind == "edge" and (c.subject, c.predicate, c.object)
            == (step["subject"], step["predicate"], step["object"])
            and c.quote == citation["quote"] for c in row.claims
        ):
            return False
    return True


def load_queries() -> tuple[list[dict], str]:
    rows, revision = read_fixture("queries.json")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 128:
        raise ValueError("invalid query fixture count")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("duplicate query fixture ID")
    for field in ("source_family", "entity_group", "template"):
        groups = {s: {r[field] for r in rows if r["split"] == s}
                  for s in ("development", "evaluation")}
        if groups["development"] & groups["evaluation"]:
            raise ValueError("fixture split overlap: " + field)
    return rows, revision


def fraction(success: int, total: int) -> dict:
    return {"success": success, "total": total,
            "rate": round(success / total, 6) if total else None}


def evaluate(demo: Showcase, *, predictions: dict | None = None, k: int = 3) -> dict:
    cases, query_revision = load_queries()
    details = []
    for case in cases:
        error, parsed, valid, supported, output = None, False, False, False, None
        try:
            output = demo.query(case["query"], k) if predictions is None else predictions[case["id"]]
            if isinstance(output, str):
                output = strict_json(output)
            parsed = isinstance(output, dict)
            valid = parsed and schema_valid(output, case["query"], demo.revision)
            supported = valid and evidence_valid(output, demo)
        except Exception as exc:
            # Missing predictions, exceptions and parse/schema failures are failed
            # cases; there is no retry or filtering of the frozen case list.
            error = type(exc).__name__
        expected = case["expected"]
        positive = expected["state"] == "ANSWERED"
        selected = [c["record_id"] for c in output["citations"]] if valid else []
        steps = [[s[key] for key in ("subject", "predicate", "object", "record_id")]
                 for s in output["steps"]] if valid else []
        selection_ok = bool(supported and output["state"] == expected["state"]
                            and selected == expected["citations"])
        # A record can contain multiple statements. Selecting its ID alone is
        # insufficient: the quoted statement must match the frozen gold answer
        # for this question, or each frozen gold edge in order.
        if selection_ok and positive:
            if expected["path"]:
                quotes = [f"{s} | {p} | {o}." for s, p, o, _ in expected["path"]]
            else:
                intent = parse(case["query"])
                quotes = [f"{intent[1]} | {intent[2]} | {expected['answer']}."] if intent else []
            selection_ok = [c["quote"] for c in output["citations"]] == quotes
        answer_ok = bool(valid and output["answer"] == expected["answer"])
        path_ok = bool(selection_ok and answer_ok and steps == expected["path"])
        reason_ok = bool(valid and (expected["reason"] is None or output["reason"] == expected["reason"]))
        exact = path_ok and reason_ok
        relevant = set(expected["relevant"])
        retrieval_valid = valid and len(output["retrieved_ids"]) <= k and all(
            node in demo.by_id for node in output["retrieved_ids"])
        hits = len(relevant & set(output["retrieved_ids"])) if retrieval_valid else 0
        details.append({"id": case["id"], "split": case["split"], "control": case["control"],
                        "query": case["query"], "positive": positive,
                        "navigation": bool(expected["path"]), "parse_valid": parsed,
                        "schema_valid": valid, "evidence_valid": supported,
                        "selection_correct": selection_ok, "answer_correct": answer_ok,
                        "navigation_correct": path_ok, "exact": exact,
                        "relevant_count": len(relevant), "retrieval_hits": hits,
                        "error": error, "output": output})

    def summarize(rows):
        positives = [r for r in rows if r["positive"]]
        negatives = [r for r in rows if not r["positive"]]
        paths = [r for r in rows if r["navigation"]]
        retrieval = [r for r in rows if r["relevant_count"]]
        return {
            "cases": len(rows),
            "parse_validity": fraction(sum(r["parse_valid"] for r in rows), len(rows)),
            "schema_validity": fraction(sum(r["schema_valid"] for r in rows), len(rows)),
            "citation_integrity": fraction(sum(r["evidence_valid"] for r in rows), len(rows)),
            "retrieval_micro_recall_at_k": fraction(sum(r["retrieval_hits"] for r in retrieval), sum(r["relevant_count"] for r in retrieval)),
            "retrieval_all_required_at_k": fraction(sum(r["retrieval_hits"] == r["relevant_count"] for r in retrieval), len(retrieval)),
            "selected_citation_correctness": fraction(sum(r["selection_correct"] for r in positives), len(positives)),
            "supported_answer_coverage": fraction(sum(r["exact"] for r in positives), len(positives)),
            "supported_navigation": fraction(sum(r["navigation_correct"] for r in paths), len(paths)),
            "abstention_correctness": fraction(sum(r["exact"] for r in negatives), len(negatives)),
            "unsafe_or_invalid_negative_output": fraction(sum(not r["schema_valid"] or r["output"]["state"] != "ABSTAIN" for r in negatives), len(negatives)),
            "exact_case_success": fraction(sum(r["exact"] for r in rows), len(rows)),
        }

    controls = defaultdict(list)
    for row in details:
        if row["control"]:
            controls[row["control"]].append(row)
    return {"schema": "szl.synthetic-showcase.evaluation/v1", "synthetic": True,
            "fixture_revision": demo.revision, "query_revision": query_revision, "k": k,
            "baseline": "Existing SecondBrainIndex TF/IDF-like overlap with TF saturation; no document-length normalization",
            "limitations": "Developer-visible, tiny synthetic software fixtures. No independent quality, model, calibration, graph-benefit or promotion claim.",
            "promotion_targets": "INCONCLUSIVE: independent sample size, confidence bounds, graph ablations and latency study not established",
            "splits": {s: summarize([r for r in details if r["split"] == s])
                       for s in ("development", "evaluation")},
            "negative_controls": {name: fraction(sum(r["exact"] for r in rows), len(rows))
                                  for name, rows in sorted(controls.items())}, "details": details}
