"""Accept actual loopback HTML/API/Anatomy behavior, not a deployed Space.

Uses only stdlib and the installed app. The test starts and reaps its own child,
uses an ephemeral loopback port, and never makes an external network request.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener


def main() -> None:
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    root = "http://127.0.0.1:" + str(port)
    opener = build_opener(ProxyHandler({}))
    def read(path):
        with opener.open(root + path, timeout=3) as response:
            assert response.headers.get("Cache-Control") == "no-store", path
            return response.read(256000).decode("utf-8")
    env = os.environ.copy()
    for key in tuple(env):
        if any(x in key.upper() for x in ("TOKEN", "SECRET", "PASSWORD", "API_KEY")):
            env.pop(key, None)
    isolated_flags = ["-I"] if sys.flags.isolated else []
    package_path = None
    if sys.flags.isolated:
        import second_brain
        package_path = Path(second_brain.__file__).resolve().parent
        assert sys.prefix != sys.base_prefix, "installed acceptance requires its own venv"
        assert package_path.is_relative_to(Path(sys.prefix).resolve()), "source checkout fallback"
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
    process = subprocess.Popen([sys.executable, *isolated_flags, "-B", "-m", "uvicorn", "second_brain.web:app",
                                "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 25
        while True:
            assert process.poll() is None, "owned test server exited before acceptance"
            try:
                observed = json.loads(read("/api/v1/lutar-lineage"))
                break
            except (URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("owned test server did not become available") from None
                time.sleep(.1)
        assert observed["observed_reference_ready"] is True
        assert len(observed["nodes"]) == 33 and len(observed["edges"]) == 32
        assert observed["coverage"]["claim_handles"] == {"observed": 8, "expected": 8}
        assert observed["coverage"]["proof_replay"]["observed"] is None
        page = read("/lutar")
        assert observed["snapshot_sha256"] in page
        assert html.escape(json.dumps(observed, indent=2, ensure_ascii=False), quote=True) in page
        assert 'href="/lutar"' in read("/")
        scenario = json.loads(read("/api/v1/lutar-lineage?scenario=withhold-source"))
        assert scenario["observed_reference_ready"] is True
        assert scenario["effective_reference_ready"] is False
        assert scenario["claims"] == [] and scenario["impact"]["files_changed"] == 0
        scenario_page = read("/lutar?scenario=withhold-source")
        assert scenario["snapshot_sha256"] in scenario_page and "hypothetical" in scenario_page
        assert read("/api/v1/lutar-lineage") == json.dumps(observed, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        # Anatomy must not reread the source when projecting its second section.
        with opener.open(root + "/api/v1/anatomy-feed", timeout=3) as response:
            anatomy = json.load(response)
        assert anatomy["lutar_lineage"] == observed
        assert anatomy["lutar_invariants"]["source_sha256"] == observed["source"]["sha256"]
        assert all(observed[k] == scenario[k] == "NONE" for k in
                   ("training_authority", "promotion_authority", "execution_authority", "merge_authority"))
        print(json.dumps({"state": "PASS", "scope": "OWNED_LOOPBACK_RUNTIME_ACCEPTANCE",
                          "snapshot_sha256": observed["snapshot_sha256"],
                          "source_sha256": observed["source"]["sha256"],
                          "nodes": len(observed["nodes"]), "edges": len(observed["edges"]),
                          "external_network_requests": 0, "deployed_space_verified": False,
                          "isolated_installed_mode": bool(sys.flags.isolated),
                          "target_package_path": str(package_path) if package_path else None}))
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.stderr:
            process.stderr.close()


if __name__ == "__main__":
    main()
