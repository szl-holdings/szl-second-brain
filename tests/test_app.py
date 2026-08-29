from fastapi.testclient import TestClient

from app import app


def test_health_and_index() -> None:
    c = TestClient(app)
    h = c.get("/health")
    assert h.status_code == 200
    body = h.json()
    assert body["lambda"] == "CONJECTURE_1"
    assert body["kind"] == "SOFTWARE"
    assert body["publication_eligible"] is False
    idx = c.get("/api/v1/index")
    assert idx.status_code == 200
    assert idx.json()["chunk_count"] == 575


def test_canvas_is_zero_cdn() -> None:
    c = TestClient(app)
    page = c.get("/")
    assert page.status_code == 200
    html = page.text
    assert "cdn." not in html.lower()
    assert "three.js" not in html.lower()
    assert "googleapis" not in html.lower()
    assert "canvas id=\"holo\"" in html
    assert "holographic" in html.lower()
    assert 'id="handles"' in html
    assert 'id="plan"' in html
    assert "/retrieve?q=" in html
    assert "/plan?q=" in html
    assert "UNAVAILABLE" in html


def test_plan_navigate_and_abstain() -> None:
    c = TestClient(app)
    nav = c.post("/api/v1/plan", json={"query": "Lambda uniqueness conjecture TH_L1"})
    assert nav.status_code == 200
    body = nav.json()
    assert body["plan"]["decision"] in ("NAVIGATE", "ABSTAIN")
    assert "graph" in body
    assert body["retrieve"]["kind"] == "SOFTWARE"
    absn = c.post(
        "/api/v1/plan",
        json={"query": "Who won the 2099 world cup according to the corpus?"},
    )
    assert absn.status_code == 200
    assert absn.json()["plan"]["decision"] == "ABSTAIN"
    assert absn.json()["plan"]["citedNodeIds"] == []


def test_get_retrieve_and_plan() -> None:
    c = TestClient(app)
    hit = c.get("/retrieve", params={"q": "Alloy data surfaces honesty doctrine", "k": 4})
    assert hit.status_code == 200
    body = hit.json()
    assert body["schema"] == "szl.second-brain.retrieve/v1"
    assert body["kind"] == "SOFTWARE"
    assert "\"text\":" not in hit.text.lower()
    nav = c.get("/plan", params={"q": "Alloy data surfaces honesty doctrine", "k": 4})
    assert nav.status_code == 200
    plan = nav.json()
    assert plan["schema"] == "szl.second-brain.plan/v1"
    assert plan["kind"] == "SOFTWARE"
    assert plan["decision"] in ("NAVIGATE", "ABSTAIN")
    empty = c.get("/api/v1/plan", params={"q": ""})
    assert empty.status_code == 200
    assert empty.json()["decision"] == "ABSTAIN"
