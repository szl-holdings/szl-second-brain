# SPDX-License-Identifier: Apache-2.0
"""Public metadata boundaries and actual handles/hydration integration."""
from __future__ import annotations

import base64
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from second_brain.frontier import AuthorizedFrontierHydrator, FrontierBoundaryError, FrontierIndex
from second_brain.public_research import (
    MAX_RESPONSE_BYTES, PublicMetadataClient, ResearchBoundaryError,
    _NoRedirect, canonical_bytes, digest, identifier_url, merge_captures,
    parse_arxiv, parse_crossref, strict_json, validate_snapshot,
)

OBSERVED = "2026-09-30T03:00:00+00:00"
DOI = "10.1002/cpa.3160130102"


def crossref(*, title="Mathematics and natural science", authors=1, doi=DOI):
    return canonical_bytes({"status": "ok", "message-type": "work", "message": {"DOI": doi, "title": [title], "author": [{"given": "Eugene", "family": "Wigner"}] * authors, "published": {"date-parts": [[1960, 2]]}}})


def atom(identifier="2305.01582v1", title="Interpretable science symbolic regression"):
    return f'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/{identifier}</id><title>{title}</title><published>2023-05-02T00:00:00Z</published><updated>2023-05-02T00:00:00Z</updated><author><name>Miles Cranmer</name></author><category term="astro-ph.IM"/></entry></feed>'''.encode()


def capture(*, raw=None, provider="crossref", identifier=DOI, observed=OBSERVED):
    return PublicMetadataClient(transport=lambda _url: raw or crossref()).capture(provider, identifier, observed_at=observed)


def snapshot():
    return merge_captures(None, [capture()])


@pytest.mark.parametrize("provider,identifier", [("crossref", "https://127.0.0.1/x"), ("arxiv", "../../etc/passwd"), ("arxiv", "2107.07511?url=http://localhost"), ("crossref", DOI + "@evil.invalid"), ("unknown", "2305.01582")])
def test_fixed_identifiers_prevent_arbitrary_network_origins(provider, identifier):
    calls = []
    client = PublicMetadataClient(transport=lambda url: calls.append(url))
    with pytest.raises(ResearchBoundaryError):
        client.capture(provider, identifier, observed_at=OBSERVED)
    assert calls == []


def test_redirects_are_denied():
    with pytest.raises(ResearchBoundaryError, match="redirect"):
        _NoRedirect().redirect_request(None, None, None, None, None, None)


def test_response_and_author_limits_do_not_relax():
    with pytest.raises(ResearchBoundaryError, match="byte bound"):
        capture(raw=b" " * (MAX_RESPONSE_BYTES + 1))
    with pytest.raises(ResearchBoundaryError, match="author count"):
        capture(raw=crossref(authors=33))


def test_crossref_identity_and_duplicate_keys_are_rejected():
    with pytest.raises(ResearchBoundaryError, match="identity"):
        parse_crossref(crossref(doi="10.1000/wrong"), DOI)
    with pytest.raises(ResearchBoundaryError, match="duplicate"):
        strict_json(b'{"status":"ok","status":"bad"}')
    with pytest.raises(ResearchBoundaryError, match="non-finite"):
        strict_json(b'{"value":NaN}')
    with pytest.raises(ResearchBoundaryError, match="non-finite"):
        strict_json(b'{"value":1e999}')


def test_metadata_sanitization_rejects_credentials_and_long_titles():
    for value in ("sk-" + "A" * 40, "a" * 241):
        with pytest.raises(ResearchBoundaryError):
            capture(raw=crossref(title=value))
    row = capture(raw=crossref(title="<b>Mathematics</b> and natural science"))
    assert row["metadata"]["title"] == "Mathematics and natural science"


def test_arxiv_version_and_xml_entities_are_rejected():
    with pytest.raises(ResearchBoundaryError, match="identity"):
        parse_arxiv(atom(identifier="2305.01582v2"), "2305.01582v1")
    with pytest.raises(ResearchBoundaryError, match="declarations"):
        parse_arxiv(b'<!DOCTYPE feed [<!ENTITY x "secret">]>' + atom(), "2305.01582")
    value = parse_arxiv(atom(), "2305.01582")
    assert value["identifier"] == "2305.01582v1"
    assert value["full_text_licence"] == "NOT_INFERRED"


@pytest.mark.parametrize("provider,identifier,response,interval", [
    ("arxiv", "2305.01582", atom(), 3.0),
    ("crossref", DOI, crossref(), 1.0),
], ids=["arxiv", "crossref"])
def test_provider_spacing_includes_failed_requests(provider, identifier, response, interval):
    clock = [0.0]
    sleeps = []
    calls = []

    def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay

    def transport(url):
        calls.append(clock[0])
        if len(calls) == 1:
            raise ResearchBoundaryError("simulated timeout")
        return response

    client = PublicMetadataClient(transport=transport, clock=lambda: clock[0], sleep=sleep)
    with pytest.raises(ResearchBoundaryError):
        client.capture(provider, identifier, observed_at=OBSERVED)
    client.capture(provider, identifier, observed_at=OBSERVED)
    assert sleeps == [interval] and calls == [0.0, interval]


@pytest.mark.parametrize("elapsed,expected_sleep", [(0.0, 1.0), (0.25, 0.75), (1.0, 0.0), (2.0, 0.0)])
def test_crossref_waits_only_for_remaining_interval(elapsed, expected_sleep):
    clock = [0.0]
    sleeps, calls = [], []

    def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay

    def transport(_url):
        calls.append(clock[0])
        return crossref()

    client = PublicMetadataClient(transport=transport, clock=lambda: clock[0], sleep=sleep)
    client.capture("crossref", DOI, observed_at=OBSERVED)
    clock[0] += elapsed
    client.capture("crossref", DOI, observed_at=OBSERVED)
    assert sleeps == ([expected_sleep] if expected_sleep else [])
    assert calls == [0.0, max(elapsed, 1.0)]


def test_crossref_batch_does_not_burst_and_preserves_capture_bytes():
    clock = [0.0]
    calls = []

    def sleep(delay):
        clock[0] += delay

    def transport(_url):
        calls.append(clock[0])
        return crossref()

    client = PublicMetadataClient(transport=transport, clock=lambda: clock[0], sleep=sleep)
    rows = [client.capture("crossref", DOI, observed_at=OBSERVED) for _ in range(12)]
    assert calls == list(range(12))
    assert all(row == rows[0] for row in rows)


def test_interleaved_providers_keep_independent_intervals():
    clock = [0.0]
    calls, sleeps = [], []

    def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay

    def transport(url):
        calls.append(("crossref" if "crossref" in url else "arxiv", clock[0]))
        return crossref() if "crossref" in url else atom()

    client = PublicMetadataClient(transport=transport, clock=lambda: clock[0], sleep=sleep)
    for provider, identifier in [("arxiv", "2305.01582"), ("crossref", DOI), ("crossref", DOI), ("arxiv", "2305.01582")]:
        client.capture(provider, identifier, observed_at=OBSERVED)
    assert calls == [("arxiv", 0.0), ("crossref", 0.0), ("crossref", 1.0), ("arxiv", 3.0)]
    assert sleeps == [1.0, 2.0]


def test_doi_case_duplicates_are_rejected_before_lock_or_network(monkeypatch, tmp_path, capsys):
    from scripts import collect_public_research as collector

    def unexpected(*_args, **_kwargs):
        raise AssertionError("duplicate requests reached lock or network")

    monkeypatch.setattr(collector.os, "open", unexpected)
    monkeypatch.setattr(collector, "PublicMetadataClient", unexpected)
    monkeypatch.setattr(collector.sys, "argv", [
        "collect_public_research.py", "--doi", DOI, "--doi", DOI.upper(),
        "--snapshot", str(tmp_path / "snapshot.json"), "--report", str(tmp_path / "report.json"),
    ])
    with pytest.raises(SystemExit) as blocked:
        collector.main()
    assert blocked.value.code == 2
    assert "distinct" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_repeated_ingestion_is_idempotent_and_changed_metadata_is_versioned():
    initial = snapshot()
    repeated = merge_captures(initial, [capture(observed="2026-09-30T04:00:00+00:00")])
    assert canonical_bytes(initial) == canonical_bytes(repeated)
    changed = merge_captures(repeated, [capture(raw=crossref(title="Mathematics and measured physics"))])
    assert len(changed["records"]) == 2
    assert changed["records"][0]["identifier"] == changed["records"][1]["identifier"]
    assert changed["records"][0]["capture_sha256"] != changed["records"][1]["capture_sha256"]


@pytest.mark.parametrize("mutation", ["digest", "metadata", "identity", "origin", "authority", "duplicate", "capture"])
def test_snapshot_tamper_and_duplicate_negatives(mutation):
    value = snapshot()
    row = value["records"][0]
    if mutation == "digest": row["capture_sha256"] = "0" * 64
    elif mutation == "metadata": row["metadata"]["title"] = "changed"
    elif mutation == "identity": row["identifier"] = "10.1000/wrong"
    elif mutation == "origin": row["request_url"] = "http://127.0.0.1/private"
    elif mutation == "authority": value["execution_authority"] = "ALLOW"
    elif mutation == "duplicate": value["records"].append(copy.deepcopy(row))
    elif mutation == "capture": row["capture_base64"] = "not base64"
    with pytest.raises(ResearchBoundaryError):
        validate_snapshot(value)


def test_stale_and_future_captures_cannot_pass_fresh_admission():
    for now in ("2027-04-01T00:00:00Z", "2026-09-01T00:00:00Z"):
        with pytest.raises(ResearchBoundaryError, match="stale"):
            validate_snapshot(snapshot(), now=now)


def test_real_packaged_research_nodes_are_handles_only_and_source_typed():
    index = FrontierIndex()
    result = index.search("Wigner natural mathematics sciences", k=4)
    handles = [handle for handle in result["handles"] if handle["kind"] == "research-metadata"]
    assert handles
    handle = handles[0]
    assert handle["revisionKind"] == "metadata-capture-sha256"
    assert len(handle["revision"]) == 64
    assert handle["sourceIdentity"]["fullTextLicence"] == "NOT_INFERRED"
    assert '"content"' not in json.dumps(result)
    assert '"capture_base64"' not in json.dumps(result)
    assert result["execution_authority"] == "NONE"
    allowed = AuthorizedFrontierHydrator(lambda *_: True, index=index)
    hydrated = allowed.hydrate([handle], principal_id="research-review", tenant_id="szl", policy_revision="review-policy")
    assert hydrated["documents"][0]["source_revision_kind"] == "metadata-capture-sha256"
    assert "Wigner" in hydrated["documents"][0]["content"]
    for field in ("revision", "path", "sourceIdentity"):
        changed = copy.deepcopy(handle)
        changed[field] = "tampered"
        with pytest.raises(FrontierBoundaryError):
            allowed.hydrate([changed], principal_id="research-review", tenant_id="szl", policy_revision="review-policy")
    with pytest.raises(FrontierBoundaryError):
        allowed.hydrate([handle, handle], principal_id="research-review", tenant_id="szl", policy_revision="review-policy")


def test_real_snapshot_has_six_distinct_projected_captures():
    value = strict_json(Path("data/public-research-metadata.v1.json").read_bytes())
    records = validate_snapshot(value)
    assert len(records) == 6
    assert {record["provider"] for record in records} == {"arxiv", "crossref"}
    for row in records:
        assert digest(base64.b64decode(row["capture_base64"])) == row["capture_sha256"]


def test_long_lived_loaded_index_rechecks_research_age_before_authorization():
    index = FrontierIndex()
    handles = [handle for handle in index.search("Wigner natural mathematics sciences")["handles"] if handle["kind"] == "research-metadata"]
    assert handles
    authorized = []
    hydrator = AuthorizedFrontierHydrator(lambda *_: authorized.append(True) or True, index=index)
    with patch("second_brain.frontier.datetime") as mocked_clock:
        mocked_clock.now.return_value = datetime(2027, 5, 1, tzinfo=timezone.utc)
        with pytest.raises(FrontierBoundaryError, match="expired"):
            hydrator.hydrate(handles, principal_id="reviewer", tenant_id="szl", policy_revision="policy")
    assert authorized == []


def test_minimal_frontier_handle_is_explicitly_denied():
    index = FrontierIndex()
    offered = index.search("Wigner natural sciences")["handles"][0]
    minimal = {key: offered[key] for key in ("nodeId", "sha256")}
    with pytest.raises(FrontierBoundaryError, match="source binding"):
        AuthorizedFrontierHydrator(lambda *_: True, index=index).hydrate([minimal], principal_id="reviewer", tenant_id="szl", policy_revision="policy")
