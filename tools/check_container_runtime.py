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
            page = response.read().decode("utf-8")
            assert 'Search evidence' in page
            # The default console carries no admission card or notice: the opt-in is off.
            assert page.count('<article class="metric">') == 3 and "HIRAG" not in page
        assert read_json("/readyz")["ready"] is True
        bundle = read_json("/api/v1/query?q=formula%20authority")
        assert bundle["retrieve"]["handles"]
        assert set(bundle["plan"]["citedNodeIds"]) <= {h["nodeId"] for h in bundle["retrieve"]["handles"]}
        assert bundle["frontier"]["state"] == "REVIEW_REQUIRED"
        capabilities = read_json("/api/v1/retrieval-capabilities")
        assert capabilities["public_content_access"] == "HANDLES_ONLY"
        # The image default: HIRAG admission is opt-in and reported as not applied, with its reason.
        assert capabilities["public_runtime_mode"] == "BM25_ONLY"
        assert capabilities["hirag_admission"]["state"] == "NOT_APPLIED"
        assert capabilities["hirag_admission"]["reason"] == "OPT_IN_NOT_ENABLED"
        ready = read_json("/readyz")
        assert set(ready["components"]) == {"corpus", "frontier", "refinement"}
        assert (ready["hirag_admission"]["state"], ready["hirag_admission"]["reason"]) == (
            "NOT_APPLIED", "OPT_IN_NOT_ENABLED")
        frontier = read_json("/api/v1/frontier-status")
        assert frontier["ready"] is True and frontier["execution_authority"] == "NONE"
        hybrid = read_json("/api/v1/hybrid?q=Lambda%20uniqueness%20conjecture")
        assert hybrid["ready"] is True and hybrid["content_access"] == "HANDLES_ONLY"
        assert hybrid["handles"] and all(
            "content" not in handle and "text" not in handle for handle in hybrid["handles"]
        )
        assert hybrid["ranking_receipt"]["admission"] == "NOT_APPLIED"
        assert hybrid["ranking_receipt"]["mode"] == capabilities["public_runtime_mode"]
        assert "admission_runtime" not in hybrid["ranking_receipt"]
        lutar = read_json("/api/v1/lutar-invariants")
        assert lutar["ready"] is True and lutar["state"] == "SOURCE_BOUND_REFERENCE"
        assert lutar["declared_locked_count"] == 8 and lutar["declared_carrier_count"] == 24
        assert [h["claimId"] for h in lutar["handles"]] == ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"]
        assert lutar["source_sha256"] == "5e0358ae4e0ff6345a42e8c2711c675fa4ec2366267205912892e9e46ecf5a6f"
        assert lutar["proof_replayed_here"] is False and lutar["runtime_refinement"] == "UNVERIFIED"
        assert all(lutar[k] == "NONE" for k in ("training_authority", "promotion_authority", "execution_authority", "merge_authority"))
        feed = read_json("/api/v1/anatomy-feed")
        assert feed["lutar_invariants"]["handles_sha256"] == lutar["handles_sha256"]
        assert all("content" not in h and "text" not in h for h in lutar["handles"])
        refinement = read_json("/api/v1/refinement-memory")
        assert refinement["ready"] is True and refinement["content_access"] == "HANDLES_ONLY"
        for route, name in (("receipt", "training_receipt.json"), ("eval", "eval_report.json")):
            expected = json.loads((Path("train") / name).read_text(encoding="utf-8"))
            assert read_json("/api/v1/" + route) == expected
        # The shipped sidecar builds the opt-in gate inside the read-only image (not served by default)
        # when it names the shipped corpus bytes; a stale sidecar must refuse to build, never fall back.
        import hashlib
        from second_brain import admission_runtime
        from second_brain._data import data_file
        from second_brain.retrieve import index
        sidecar_path = data_file(admission_runtime.METADATA_FILE)
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        shipped = hashlib.sha256(data_file("brain-corpus.public.jsonl").read_bytes()).hexdigest()
        if sidecar["corpus_sha256"] == shipped:
            _gated, block = admission_runtime.build_runtime(index(), sidecar_path)
            assert block["state"] == "CONFIGURED" and block["corpus_row_count"] == health["chunk_count"]
            assert block["declared_license_count"] == 0 and block["unknown_license_count"] == health["chunk_count"]
        else:
            try:
                admission_runtime.build_runtime(index(), sidecar_path)
            except admission_runtime.AdmissionBlocked as exc:
                assert exc.reason == "METADATA_GENERATION_MISMATCH", exc.reason
            else:
                raise AssertionError("a stale admission sidecar built a gate")
        print("container runtime closure passed: corpus, UI, Lutar/Anatomy handles, retained records, "
              "and opt-in HIRAG admission sidecar")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()
