from __future__ import annotations

import io
import urllib.error

import pytest

from scripts import refresh_frontier_memory as refresh


@pytest.mark.parametrize("status", [401, 403, 429])
def test_authenticated_http_failure_does_not_retry_anonymously(monkeypatch, status) -> None:
    identities = []

    def urlopen(request, *, timeout):
        identity = request.get_header("Authorization")
        identities.append(identity)
        if identity:
            raise urllib.error.HTTPError(request.full_url, status, "blocked", {}, None)
        return io.BytesIO(b"[]")

    monkeypatch.setattr(refresh.urllib.request, "urlopen", urlopen)
    with pytest.raises(refresh.RefreshError, match="fetch failed: HTTPError"):
        refresh._github_json("https://api.github.com/repos/example/public/commits", "synthetic-token")
    assert identities == ["Bearer synthetic-token"]


def test_oversized_authenticated_response_is_not_retried_anonymously(monkeypatch) -> None:
    identities = []

    def urlopen(request, *, timeout):
        identity = request.get_header("Authorization")
        identities.append(identity)
        return io.BytesIO(b"x" * (512 * 1024 + 1) if identity else b"[]")

    monkeypatch.setattr(refresh.urllib.request, "urlopen", urlopen)
    with pytest.raises(refresh.RefreshError, match="source exceeded"):
        refresh._github_json("https://api.github.com/repos/example/public/commits", "synthetic-token")
    assert identities == ["Bearer synthetic-token"]


@pytest.mark.parametrize("token", [None, "synthetic-token"])
def test_successful_request_preserves_the_selected_identity(monkeypatch, token) -> None:
    identities = []

    def urlopen(request, *, timeout):
        identities.append(request.get_header("Authorization"))
        return io.BytesIO(b'[{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]')

    monkeypatch.setattr(refresh.urllib.request, "urlopen", urlopen)
    assert refresh.resolve_path_revision(refresh.SOURCES[0], token=token) == "a" * 40
    assert identities == [f"Bearer {token}" if token else None]


def test_rate_limited_refresh_leaves_existing_snapshot_untouched(monkeypatch, tmp_path) -> None:
    candidates = tmp_path / "candidates.jsonl"
    state = tmp_path / "state.json"
    old_candidates = b"previous candidate bytes\n"
    old_state = b'{"state":"previous"}\n'
    candidates.write_bytes(old_candidates)
    state.write_bytes(old_state)
    identities = []

    def urlopen(request, *, timeout):
        identities.append(request.get_header("Authorization"))
        raise urllib.error.HTTPError(request.full_url, 429, "rate limited", {}, None)

    monkeypatch.setattr(refresh.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(refresh, "environment_token", lambda: "synthetic-token")
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    monkeypatch.setattr(refresh.sys, "argv", [
        "refresh_frontier_memory.py", "--candidates", str(candidates), "--state", str(state),
    ])

    with pytest.raises(refresh.RefreshError, match="fetch failed: HTTPError"):
        refresh.main()
    assert identities == ["Bearer synthetic-token"]
    assert candidates.read_bytes() == old_candidates
    assert state.read_bytes() == old_state
