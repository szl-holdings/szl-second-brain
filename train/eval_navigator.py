#!/usr/bin/env python3
"""Named-N retrieve-hit and abstain bench. Train loss is not eval.

SOFTWARE index is always scored. Generate is MEASURED only if a local adapter
loads and emits parseable JSON; otherwise UNAVAILABLE. Never claim 5/5 unless
the denominator was actually run.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from second_brain.plan import plan_from_handles  # noqa: E402
from second_brain.retrieve import SecondBrainIndex  # noqa: E402

RETRIEVE_GATE = HERE / "gate_retrieve.jsonl"
ABSTAIN_GATE = HERE / "gate_abstain.jsonl"
REPORT = HERE / "eval_report.json"
ADAPTER = HERE / "brain-navigator-r2-adapter"
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
JSON_RE = re.compile(r"\{.*\}", re.S)


def _load(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _parse_plan(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = JSON_RE.search(raw)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def software_bench(idx: SecondBrainIndex) -> dict[str, Any]:
    retrieve = _load(RETRIEVE_GATE)
    abstain = _load(ABSTAIN_GATE)
    retrieve_cases = []
    hit = 0
    for row in retrieve:
        q = row["query"]
        expect = list(row.get("expect_cite") or [])
        got = idx.search(q, k=5)
        ids = [h["nodeId"] for h in got["handles"]]
        ok = bool(expect) and expect[0] in ids
        if ok:
            hit += 1
        plan = plan_from_handles(q, got["handles"])
        retrieve_cases.append(
            {
                "id": row["id"],
                "query": q,
                "expect_cite": expect,
                "got_ids": ids,
                "hit": ok,
                "plan_decision": plan["decision"],
                "plan_cite": plan["citedNodeIds"],
            }
        )
    abs_cases = []
    abs_ok = 0
    for row in abstain:
        q = row["query"]
        plan = plan_from_handles(q, row.get("handles") or [])
        ok = plan["decision"] == "ABSTAIN" and not plan["citedNodeIds"]
        if ok:
            abs_ok += 1
        abs_cases.append(
            {
                "id": row["id"],
                "query": q,
                "decision": plan["decision"],
                "citedNodeIds": plan["citedNodeIds"],
                "ok": ok,
            }
        )
    return {
        "kind": "SOFTWARE",
        "label": "MEASURED",
        "retrieve_hit": f"{hit}/{len(retrieve)}" if retrieve else "0/0",
        "retrieve_hit_correct": hit,
        "retrieve_hit_total": len(retrieve),
        "abstain": f"{abs_ok}/{len(abstain)}" if abstain else "0/0",
        "abstain_correct": abs_ok,
        "abstain_total": len(abstain),
        "retrieve_cases": retrieve_cases,
        "abstain_cases": abs_cases,
        "honesty": (
            "Lexical rank over the PUBLIC 575-chunk projection. "
            "Score is overlap, never correctness. Named-N gates."
        ),
    }


def generate_bench() -> dict[str, Any]:
    if not (ADAPTER / "adapter_config.json").is_file():
        return {
            "kind": "GENERATE",
            "label": "UNAVAILABLE",
            "reason": "no local adapter; SOFTWARE navigator is the shipped planner",
            "publication_eligible": False,
        }
    try:
        import torch
        from unsloth import FastLanguageModel
    except Exception as exc:  # noqa: BLE001
        return {
            "kind": "GENERATE",
            "label": "UNAVAILABLE",
            "reason": f"unsloth/torch import failed: {exc}",
            "publication_eligible": False,
        }
    if not torch.cuda.is_available():
        return {
            "kind": "GENERATE",
            "label": "UNAVAILABLE",
            "reason": "CUDA UNAVAILABLE for generate",
            "publication_eligible": False,
        }
    try:
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=str(ADAPTER),
            max_seq_length=2048,
            load_in_4bit=False,
            load_in_16bit=True,
        )
        FastLanguageModel.for_inference(model)
    except Exception as exc:  # noqa: BLE001
        return {
            "kind": "GENERATE",
            "label": "UNAVAILABLE",
            "reason": f"adapter load failed: {type(exc).__name__}: {exc}",
            "publication_eligible": False,
        }

    def infer(query: str, handles: list[dict[str, Any]]) -> dict[str, Any] | None:
        user = query + "\n\nCANDIDATE_HANDLES_JSON:\n" + json.dumps(handles)
        messages = [
            {"role": "system", "content": SYS},
            {"role": "user", "content": user},
        ]
        # Qwen3.5 ships a multimodal processor; tokenize text only.
        try:
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        tok = getattr(tokenizer, "tokenizer", tokenizer)
        encoded = tok(prompt, return_tensors="pt", add_special_tokens=False)
        input_ids = encoded["input_ids"].to(model.device)
        attn = encoded.get("attention_mask")
        gen_kw: dict[str, Any] = {
            "input_ids": input_ids,
            "max_new_tokens": 512,
            "do_sample": False,
        }
        if attn is not None:
            gen_kw["attention_mask"] = attn.to(model.device)
        out = model.generate(**gen_kw)
        text = tok.decode(out[0][input_ids.shape[-1] :], skip_special_tokens=True)
        return _parse_plan(text)

    retrieve = _load(RETRIEVE_GATE)
    abstain = _load(ABSTAIN_GATE)
    nav_ok = 0
    abs_ok = 0
    halluc = 0
    cases: list[dict[str, Any]] = []
    parse_fail = 0
    try:
        for row in retrieve:
            plan = infer(row["query"], row["handles"])
            if not plan:
                parse_fail += 1
                cases.append({"id": row["id"], "ok": False, "reason": "unparseable"})
                continue
            offered = {h["nodeId"] for h in row["handles"]}
            cites = list(plan.get("citedNodeIds") or [])
            if any(c not in offered for c in cites):
                halluc += 1
            expect = list(row.get("expect_cite") or [])
            ok = (
                plan.get("decision") == "NAVIGATE"
                and bool(expect)
                and expect[0] in cites
                and all(c in offered for c in cites)
            )
            if ok:
                nav_ok += 1
            cases.append(
                {
                    "id": row["id"],
                    "decision": plan.get("decision"),
                    "citedNodeIds": cites,
                    "ok": ok,
                }
            )
        for row in abstain:
            plan = infer(row["query"], row["handles"])
            if not plan:
                parse_fail += 1
                cases.append({"id": row["id"], "ok": False, "reason": "unparseable"})
                continue
            offered = {h["nodeId"] for h in row["handles"]}
            cites = list(plan.get("citedNodeIds") or [])
            if any(c not in offered for c in cites):
                halluc += 1
            ok = plan.get("decision") == "ABSTAIN" and not cites
            if ok:
                abs_ok += 1
            cases.append(
                {
                    "id": row["id"],
                    "decision": plan.get("decision"),
                    "citedNodeIds": cites,
                    "ok": ok,
                }
            )
    except Exception as exc:  # noqa: BLE001
        return {
            "kind": "GENERATE",
            "label": "UNAVAILABLE",
            "reason": f"generate failed: {type(exc).__name__}: {exc}",
            "publication_eligible": False,
        }
    return {
        "kind": "GENERATE",
        "label": "MEASURED",
        "retrieve_hit": f"{nav_ok}/{len(retrieve)}" if retrieve else "0/0",
        "retrieve_hit_correct": nav_ok,
        "retrieve_hit_total": len(retrieve),
        "abstain": f"{abs_ok}/{len(abstain)}" if abstain else "0/0",
        "abstain_correct": abs_ok,
        "abstain_total": len(abstain),
        "hallucinated_citation_count": halluc,
        "parse_fail": parse_fail,
        "cases": cases,
        "publication_eligible": False,
        "honesty": (
            "Owner-run named-N generate on local LoRA. Not a third-party bench. "
            "Train loss is not this number. publication_eligible stays false."
        ),
    }


def main() -> int:
    idx = SecondBrainIndex()
    software = software_bench(idx)
    generate = generate_bench()
    report = {
        "schema": "szl.brain-navigator-r2.eval/v1",
        "artifact": "SZLHOLDINGS/brain-navigator-r2",
        "does_not_overwrite": "SZLHOLDINGS/SZL-Khipu-1.5B-BrainNavigator",
        "lambda": "Conjecture 1",
        "doctrine": "v11 LOCKED",
        "publication_eligible": False,
        "maturity": "MEASURED_RESEARCH_ONLY",
        "train_loss_is_eval": False,
        "raw_graph_nodes_admitted_to_gradients": 0,
        "corpus_n": idx.n,
        "software": software,
        "generate": generate,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "honesty": (
            "Do not claim 5/5 unless MEASURED. Existing 1.5B BrainNavigator "
            "abstain 2/6 is a different SKU and is not restated as this run."
        ),
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "SOFTWARE retrieve-hit "
        f"{software['retrieve_hit']} abstain {software['abstain']} "
        f"GENERATE {generate['label']} "
        f"{generate.get('retrieve_hit', 'n/a')} / {generate.get('abstain', 'n/a')}"
    )
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
