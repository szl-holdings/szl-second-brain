"""Accept the wheel's public web surface outside the checkout, without network.

Run with the isolated interpreter of a clean wheel-install venv, from a directory
outside the checkout. The test extra supplies FastAPI's in-process HTTP client.
No server, provider, training job, or signing operation is started.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import importlib.metadata
import json
from pathlib import Path
import sys
import sysconfig
from unittest.mock import patch


def reject_network(*_args, **_kwargs):
    raise AssertionError("installed-web acceptance must not open network connections")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    checkout = parser.parse_args().checkout.resolve()
    assert sys.flags.isolated, "run this acceptance with python -I"
    assert sys.prefix != sys.base_prefix, "a separate wheel-install venv is required"
    assert not Path.cwd().resolve().is_relative_to(checkout), "run outside the checkout"
    assert all(not Path(p).resolve().is_relative_to(checkout) for p in sys.path), sys.path

    with ExitStack() as stack:
        for target in ("socket.create_connection", "socket.socket.connect",
                       "socket.socket.connect_ex"):
            stack.enter_context(patch(target, side_effect=reject_network))

        import second_brain
        from fastapi.testclient import TestClient
        import second_brain.routes_legacy as routes_legacy
        from second_brain.retrieve import canonical_sha256
        from second_brain.web import app

        package = Path(second_brain.__file__).resolve().parent
        purelib = Path(sysconfig.get_path("purelib")).resolve()
        distribution = importlib.metadata.distribution("szl-second-brain")
        assert package == purelib / "second_brain", package
        assert package == Path(distribution.locate_file("second_brain")).resolve()
        assert second_brain.__version__ == distribution.version
        # Even optional record reads must not fall back to the source checkout.
        assert routes_legacy.STATIC.resolve() == package / "static"
        assert not routes_legacy.RECEIPT.exists(), "wheel unexpectedly contains training records"
        assert not routes_legacy.EVAL.exists(), "wheel unexpectedly contains evaluation records"

        with TestClient(app) as client:
            ready = client.get("/readyz")
            assert ready.status_code == 200, ready.text
            assert ready.json()["ready"] is True
            assert all(c["ready"] for c in ready.json()["components"].values())
            assert ready.json()["execution_authority"] == "NONE"
            assert ready.json()["model_generation"] == "NOT_CONFIGURED"

            query = {"q": "formula authority", "k": 4}
            response = client.get("/api/v1/query", params=query)
            assert response.status_code == 200, response.text
            bundle = response.json()
            assert bundle["ready"] is True
            assert bundle["content_access"] == "HANDLES_ONLY"
            assert bundle["execution_authority"] == "NONE"
            handles = bundle["retrieve"]["handles"]
            assert handles and bundle["frontier"]["handles"]
            assert bundle["frontier"]["state"] == "REVIEW_REQUIRED"
            assert set(bundle["plan"]["citedNodeIds"]) <= {h["nodeId"] for h in handles}
            assert all("text" not in h and "content" not in h for h in handles)
            receipt = dict(bundle["receipt"])
            checksum = receipt.pop("sha256")
            assert checksum == canonical_sha256(receipt)
            assert receipt["handles_sha256"] == canonical_sha256(handles)
            assert receipt["plan_sha256"] == canonical_sha256(bundle["plan"])
            assert receipt["signature"] == "UNSIGNED_CONTENT_DIGEST"
            post = client.post("/api/v1/query", json=query)
            assert post.status_code == 200 and post.json() == bundle

            console = client.get("/", params=query)
            assert console.status_code == 200, console.text
            assert "Search evidence" in console.text
            assert checksum in console.text and handles[0]["nodeId"] in console.text
            hologram = client.get("/hologram")
            assert hologram.status_code == 200, hologram.text
            assert "/api/v1/query" in hologram.text
            assert hologram.text == (package / "static" / "index.html").read_text(encoding="utf-8")

            for route, filename in (("receipt", "training_receipt.json"),
                                    ("eval", "eval_report.json")):
                optional = client.get("/api/v1/" + route)
                assert optional.status_code == 200
                assert optional.json() == {"label": "UNAVAILABLE",
                                           "reason": filename + " not present"}
            # Missing optional records do not make the public retrieval service unavailable.
            assert client.get("/readyz").json()["ready"] is True

        for name, module in tuple(sys.modules.items()):
            if name == "second_brain" or name.startswith("second_brain."):
                location = getattr(module, "__file__", None)
                if location:
                    assert Path(location).resolve().is_relative_to(package), (name, location)
        print(json.dumps({"state": "PASS", "scope": "INSTALLED_WHEEL_WEB_ACCEPTANCE",
                          "version": distribution.version, "package_path": str(package),
                          "routes": ["/", "/hologram", "/readyz", "/api/v1/query",
                                     "/api/v1/receipt", "/api/v1/eval"],
                          "optional_training_records": "UNAVAILABLE",
                          "network": "FORBIDDEN", "execution_authority": "NONE"}, sort_keys=True))


if __name__ == "__main__":
    main()
