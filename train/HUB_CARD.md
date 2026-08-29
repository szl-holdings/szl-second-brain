---
license: apache-2.0
base_model: Qwen/Qwen3.5-0.8B
library_name: peft
pipeline_tag: text-generation
tags:
  - lora
  - unsloth
  - governed-agent
  - retrieval
  - brain-navigator
  - szl-holdings
---

# BrainNavigator-R2

Separate 0.8B LoRA SKU. **Does not overwrite**
[`SZLHOLDINGS/SZL-Khipu-1.5B-BrainNavigator`](https://huggingface.co/SZLHOLDINGS/SZL-Khipu-1.5B-BrainNavigator)
or [`SZLHOLDINGS/SZL-Khipu-1.5B`](https://huggingface.co/SZLHOLDINGS/SZL-Khipu-1.5B).

| | |
|---|---|
| Base | `Qwen/Qwen3.5-0.8B` Apache-2.0 |
| Quant | **bf16 LoRA** r=16 α=32. QLoRA forbidden on Qwen3.5. |
| GPU | RTX 5050 Laptop 8GB **Blackwell** |
| Curriculum | synthetic NAVIGATE/ABSTAIN over **575 public handles** |
| Private graph | 9464 nodes admitted to gradients = **0** |
| publication_eligible | **false** until MEASURED generate |
| Λ | Conjecture 1 — never a theorem |

Train loss is not eval. Named-N generate lives in `eval_report.json`.
Software retrieval hologram: [SZLHOLDINGS/second-brain](https://huggingface.co/spaces/SZLHOLDINGS/second-brain).
