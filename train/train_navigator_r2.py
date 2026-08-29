#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "unsloth",
#     "trl>=0.12.0",
#     "peft>=0.7.0",
#     "datasets",
#     "transformers>=5.0.0",
# ]
# ///
"""BrainNavigator-R2 Unsloth bf16 LoRA kit. Separate SKU.

Base: Qwen/Qwen3.5-0.8B (Apache-2.0).
Hub id SZLHOLDINGS/brain-navigator-r2 — never overwrite
SZLHOLDINGS/SZL-Khipu-1.5B-BrainNavigator or SZLHOLDINGS/SZL-Khipu-1.5B.

Unsloth 2026-08: QLoRA is not recommended on Qwen3.5.
bf16 LoRA r=16 α=32, seed 11, response-only CE.
Trains only train/train.jsonl (synthetic routing over PUBLIC 575 handles).
Refuses gate_*.jsonl (eval-only named-N files).
Raw 9464-node graph admitted to gradients = 0.

publication_eligible false until MEASURED generate. Train loss is not eval.
Λ = Conjecture 1. Doctrine v11 LOCKED.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TRAIN_FILE = HERE / "train.jsonl"
CANONICAL_BASE = "Qwen/Qwen3.5-0.8B"
BASE_TRAIN = "Qwen/Qwen3.5-0.8B"
DEFAULT_HUB = "SZLHOLDINGS/brain-navigator-r2"
FORBIDDEN_HUBS = (
    "SZLHOLDINGS/SZL-Khipu-1.5B-BrainNavigator",
    "SZLHOLDINGS/SZL-Khipu-1.5B",
    "SZLHOLDINGS/SZL-Khipu-1.5B-GGUF",
)
MAX_SEQ_LEN = 2048
SEED = 11
LORA_R = 16
LORA_ALPHA = 32
LR = 2e-4
NUM_EPOCHS = 3
WARMUP_STEPS = 6
ADAPTER_DIR = HERE / "brain-navigator-r2-adapter"
TRAIN_RECEIPT = HERE / "training_receipt.json"


def refuse_qlora_runtime(runtime: str) -> None:
    lower = runtime.lower()
    if "4bit" in lower or "bnb" in lower or "qlora" in lower:
        raise SystemExit(
            "[brain-nav-r2] refuse: QLoRA/4bit runtime forbidden on Qwen3.5. "
            "Unsloth 2026-08: use bf16 LoRA (load_in_4bit=False, load_in_16bit=True)."
        )


def refuse_overwrite(hub: str) -> None:
    normalized = hub.strip().rstrip("/")
    upper = normalized.upper()
    for forbidden in FORBIDDEN_HUBS:
        if upper == forbidden.upper() or upper.startswith(forbidden.upper() + "/"):
            raise SystemExit(
                f"[brain-nav-r2] refuse: never overwrite {forbidden}. "
                f"This SKU is {DEFAULT_HUB} only."
            )
    if "KHIPU-1.5B" in upper or "BRAINNAVIGATOR" in upper and "R2" not in upper:
        raise SystemExit(
            f"[brain-nav-r2] refuse: hub {hub!r} collides with the 1.5B SKU. "
            f"Use {DEFAULT_HUB}."
        )
    if normalized != DEFAULT_HUB:
        raise SystemExit(
            f"[brain-nav-r2] refuse: hub {normalized!r} is not {DEFAULT_HUB}."
        )


def refuse_gate_ingest(path: Path) -> None:
    name = path.name.lower()
    if name.startswith("gate_") or "gate" in path.parts:
        raise SystemExit(
            f"[brain-nav-r2] refuse: will not ingest eval-only named-N file {path}."
        )


def gpu_receipt() -> dict[str, Any]:
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free,driver_version",
                "--format=csv,noheader",
            ],
            text=True,
            timeout=20,
        ).strip()
        info["nvidia_smi"] = out
    except Exception as exc:  # noqa: BLE001
        info["nvidia_smi_error"] = str(exc)
    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["gpu_mem_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / 1024**3, 2
            )
    except Exception as exc:  # noqa: BLE001
        info["torch_error"] = str(exc)
    return info


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_safetensors_dir(directory: Path) -> str:
    files = sorted(glob.glob(str(directory / "*.safetensors")))
    if not files:
        return ""
    digest = hashlib.sha256()
    for path in files:
        digest.update(os.path.basename(path).encode("utf-8"))
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    return digest.hexdigest()


def load_train_rows(dataset_file: Path | None = None) -> tuple[list[dict[str, Any]], str]:
    path = Path(dataset_file) if dataset_file is not None else TRAIN_FILE
    refuse_gate_ingest(path)
    if not path.is_file():
        raise SystemExit(f"[brain-nav-r2] refuse: missing curriculum {path}")
    rows: list[dict[str, Any]] = []
    nav = 0
    absn = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "messages" not in row:
            raise SystemExit(f"[brain-nav-r2] refuse: row missing messages in {path}")
        assistant = row["messages"][-1]["content"]
        gold = json.loads(assistant)
        if gold.get("artifact") != DEFAULT_HUB:
            raise SystemExit(
                f"[brain-nav-r2] refuse: train JSON artifact must be {DEFAULT_HUB}"
            )
        if gold.get("base_model") != CANONICAL_BASE:
            raise SystemExit(
                "[brain-nav-r2] refuse: train JSON base_model must be CANONICAL_BASE"
            )
        if gold.get("contentAccess") != "HANDLES_ONLY":
            raise SystemExit("[brain-nav-r2] refuse: contentAccess must be HANDLES_ONLY")
        if gold.get("decision") == "ABSTAIN":
            absn += 1
        else:
            nav += 1
        rows.append({"messages": row["messages"]})
    if nav < 1 or absn < 1:
        raise SystemExit("[brain-nav-r2] refuse: curriculum needs NAVIGATE and ABSTAIN")
    digest = sha256_file(path)
    print(f"[brain-nav-r2] examples={len(rows)} navigate={nav} abstain={absn} sha256={digest}")
    return rows, digest


def status_receipt(
    *,
    hub: str,
    dataset_sha: str,
    live: bool = False,
    training_loss: str | None = None,
    adapter_sha: str = "",
    training_rows: int | None = None,
    reason: str | None = None,
    gpu: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": "szl-brain-navigator-r2-training-receipt",
        "schema": "szl.frontier-training-run/v1",
        "v": 1,
        "artifact": hub,
        "sku": "BRAIN-NAVIGATOR-R2",
        "does_not_overwrite": list(FORBIDDEN_HUBS),
        "canonical_base": CANONICAL_BASE,
        "base_model": CANONICAL_BASE,
        "qlora": False,
        "load_in_4bit": False,
        "load_in_16bit": True,
        "quant": "bf16-lora",
        "lora_r": LORA_R,
        "lora_alpha": LORA_ALPHA,
        "seed": SEED,
        "num_train_epochs": NUM_EPOCHS,
        "warmup_steps": WARMUP_STEPS,
        "learning_rate": LR,
        "lr_scheduler_type": "constant_with_warmup",
        "optim": "adamw_8bit",
        "response_only_loss": True,
        "max_seq_length": MAX_SEQ_LEN,
        "dataset_file": "train/train.jsonl",
        "dataset_sha256": dataset_sha,
        "held_out_in_gradients": False,
        "raw_graph_nodes_admitted_to_gradients": 0,
        "public_chunk_count": 575,
        "push_to_hub": False,
        "trackio": False,
        "report_to": "none",
        "weights": "LOCAL" if adapter_sha else "UNAVAILABLE",
        "adapterSha256": adapter_sha or None,
        "finalTrainLoss": training_loss,
        "train_loss_label": "MEASURED" if training_loss else "UNAVAILABLE",
        "evals": "none-this-run",
        "quality": "UNAVAILABLE",
        "lambda": "Conjecture 1",
        "doctrine": "v11 LOCKED 749/14/163",
        "proposal_only": True,
        "publication_eligible": False,
        "autonomy_eligible": False,
        "hub_put": False,
        "training_rows": training_rows,
        "reason": reason,
        "gpu": gpu,
        "claim_boundary": (
            f"Separate SKU {DEFAULT_HUB}. Does not overwrite the 1.5B BrainNavigator. "
            "Train loss is not eval. publication_eligible false until MEASURED generate. "
            "Curriculum is synthetic routing over PUBLIC 575-chunk handles. "
            "Raw 9464-node graph admitted to gradients = 0. Λ = Conjecture 1."
        ),
        "computed_at": datetime.now(timezone.utc).isoformat() if live else None,
        "source": "local-train" if live else "forge-status",
    }


def write_receipt(payload: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[brain-nav-r2] wrote {path}")


def train_main(hub: str, dataset_file: Path | None) -> int:
    refuse_overwrite(hub)
    refuse_qlora_runtime(BASE_TRAIN)
    if LORA_R != 16 or LORA_ALPHA != 32:
        raise SystemExit("[brain-nav-r2] refuse: owner pin is r=16 alpha=32")
    rows, digest = load_train_rows(dataset_file)
    gpu = gpu_receipt()
    print(f"[brain-nav-r2] gpu={gpu}")
    if not gpu.get("cuda"):
        write_receipt(
            status_receipt(
                hub=hub,
                dataset_sha=digest,
                live=True,
                training_rows=len(rows),
                reason="CUDA UNAVAILABLE — SOFTWARE navigator ships without weights",
                gpu=gpu,
            ),
            TRAIN_RECEIPT,
        )
        print("[brain-nav-r2] CUDA UNAVAILABLE; skipping Unsloth train")
        return 0

    from datasets import Dataset
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import train_on_responses_only
    from trl import SFTConfig, SFTTrainer

    print(
        f"[brain-nav-r2] train base={CANONICAL_BASE} hub={hub} "
        f"seed={SEED} r={LORA_R} alpha={LORA_ALPHA}"
    )
    print("[brain-nav-r2] push_to_hub=false; QLoRA forbidden")

    try:
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=BASE_TRAIN,
            max_seq_length=MAX_SEQ_LEN,
            load_in_4bit=False,
            load_in_16bit=True,
            full_finetuning=False,
        )
        model = FastLanguageModel.get_peft_model(
            model,
            r=LORA_R,
            lora_alpha=LORA_ALPHA,
            lora_dropout=0,
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=SEED,
            max_seq_length=MAX_SEQ_LEN,
        )
        texts = [
            tokenizer.apply_chat_template(
                row["messages"], tokenize=False, add_generation_prompt=False
            )
            for row in rows
        ]
        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=Dataset.from_dict({"text": texts}),
            dataset_text_field="text",
            max_seq_length=MAX_SEQ_LEN,
            args=SFTConfig(
                per_device_train_batch_size=1,
                gradient_accumulation_steps=2,
                num_train_epochs=NUM_EPOCHS,
                learning_rate=LR,
                warmup_steps=WARMUP_STEPS,
                logging_steps=1,
                optim="adamw_8bit",
                weight_decay=0.01,
                lr_scheduler_type="constant_with_warmup",
                seed=SEED,
                output_dir=str(HERE / "outputs"),
                report_to="none",
                push_to_hub=False,
                save_strategy="no",
                bf16=True,
            ),
        )
        try:
            trainer = train_on_responses_only(
                trainer,
                instruction_part="<|im_start|>user\n",
                response_part="<|im_start|>assistant\n",
                tokenizer=tokenizer,
            )
        except TypeError:
            trainer = train_on_responses_only(
                trainer,
                instruction_part="<|im_start|>user\n",
                response_part="<|im_start|>assistant\n",
            )
        print("[brain-nav-r2] training...")
        stats = trainer.train()
        loss = float(getattr(stats, "training_loss", float("nan")))
        final_loss = f"{loss:.4f}" if loss == loss else "UNAVAILABLE"
        print(
            f"[brain-nav-r2] train_loss MEASURED {final_loss} "
            "(train metric, not an eval)"
        )
        ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(ADAPTER_DIR)
        tokenizer.save_pretrained(ADAPTER_DIR)
        adapter_sha = sha256_safetensors_dir(ADAPTER_DIR)
        print(f"[brain-nav-r2] local adapter {ADAPTER_DIR} sha256={adapter_sha}")
        receipt = status_receipt(
            hub=hub,
            dataset_sha=digest,
            live=True,
            training_loss=final_loss,
            adapter_sha=adapter_sha,
            training_rows=len(texts),
            gpu=gpu,
        )
        receipt["qlora"] = False
        receipt["load_in_4bit"] = False
        receipt["load_in_16bit"] = True
        write_receipt(receipt, TRAIN_RECEIPT)
        return 0
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        oom = "out of memory" in msg.lower() or "oom" in msg.lower()
        reason = f"OOM: {msg}" if oom else f"train failed: {type(exc).__name__}: {msg}"
        print(f"[brain-nav-r2] {reason}")
        write_receipt(
            status_receipt(
                hub=hub,
                dataset_sha=digest,
                live=True,
                training_rows=len(rows),
                reason=reason,
                gpu=gpu,
            ),
            TRAIN_RECEIPT,
        )
        return 2


def status_main(hub: str, dataset_file: Path | None) -> int:
    refuse_overwrite(hub)
    rows, digest = load_train_rows(dataset_file)
    write_receipt(
        status_receipt(hub=hub, dataset_sha=digest, training_rows=len(rows), gpu=gpu_receipt()),
        TRAIN_RECEIPT,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--hub", default=os.environ.get("HUB_MODEL_ID", DEFAULT_HUB))
    parser.add_argument("--dataset-file", type=Path)
    args = parser.parse_args()
    refuse_overwrite(args.hub)
    if args.train:
        return train_main(args.hub, args.dataset_file)
    return status_main(args.hub, args.dataset_file)


if __name__ == "__main__":
    raise SystemExit(main())
