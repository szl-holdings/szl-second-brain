"""Exercise the actual image's runtime file closure without external network access."""

import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


def read_json(path: str):
    with urlopen("http://127.0.0.1:7860" + path, timeout=3) as response:
        return json.load(response)


def main() -> None:
    for excluded in (".git", ".github", "tests", "train/train.jsonl",
                     "train/gate_abstain.jsonl", "train/build_curriculum.py"):
        assert not Path(excluded).exists(), f"non-runtime input shipped: {excluded}"
    process = subprocess.Popen([
        sys.executable, "-m", "uvicorn", "app_refinement:app",
        "--host", "127.0.0.1", "--port", "7860",
    ])
    try:
        deadline = time.monotonic() + 20
        while True:
            assert process.poll() is None, "runtime exited before health check"
            try:
                health = read_json("/health")
                break
            except (URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("runtime did not start")
                time.sleep(0.1)
        assert health["ok"] is True and health["chunk_count"] == 575
        assert health["publication_eligible"] is False
        with urlopen("http://127.0.0.1:7860/", timeout=3) as response:
            assert 'canvas id="holo"' in response.read().decode("utf-8")
        capabilities = read_json("/api/v1/retrieval-capabilities")
        assert capabilities["public_content_access"] == "HANDLES_ONLY"
        frontier = read_json("/api/v1/frontier-status")
        assert frontier["ready"] is True and frontier["execution_authority"] == "NONE"
        hybrid = read_json("/api/v1/hybrid?q=Lambda%20uniqueness%20conjecture")
        assert hybrid["ready"] is True and hybrid["content_access"] == "HANDLES_ONLY"
        assert hybrid["handles"] and all(
            "content" not in handle and "text" not in handle for handle in hybrid["handles"]
        )
        refinement = read_json("/api/v1/refinement-memory")
        assert refinement["ready"] is True and refinement["content_access"] == "HANDLES_ONLY"
        for route, name in (("receipt", "training_receipt.json"), ("eval", "eval_report.json")):
            expected = json.loads((Path("train") / name).read_text(encoding="utf-8"))
            assert read_json("/api/v1/" + route) == expected
        print("container runtime closure passed: corpus, UI, handles, and retained records")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()
