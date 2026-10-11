from __future__ import annotations

import hashlib

import pytest

from scripts.refresh_frontier_memory import (
    MAX_CANDIDATE_CHARS,
    MAX_TEXT_CANDIDATES,
    RefreshError,
    SourceSpec,
    markdown_candidates,
)


SPEC = SourceSpec("synthetic_readme", "example/synthetic", "README.md", "markdown")
REVISION = "a" * 40
CONTENT = "Substantive source documentation with enough detail for a review candidate."


def document(sections: list[tuple[str, str]]) -> bytes:
    return "\n".join(f"## {title}\n{body}" for title, body in sections).encode("utf-8")


def expected_id(index: int, title: str) -> str:
    identity = f"example/synthetic\x00README.md\x00source-document\x00section:{index}:{title}"
    return "frontier:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


@pytest.mark.parametrize("short_count", [MAX_TEXT_CANDIDATES, 100])
def test_short_sections_do_not_hide_later_substantive_content(short_count: int) -> None:
    sections = [(f"Navigation {index}", "x") for index in range(short_count)]
    rows = markdown_candidates(SPEC, REVISION, document(sections + [("Details", CONTENT)]))

    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == expected_id(short_count, "Details")
    assert row["content"] == CONTENT
    assert row["content_sha256"] == hashlib.sha256(CONTENT.encode("utf-8")).hexdigest()
    assert row["source_repository"] == SPEC.repository
    assert row["source_path"] == SPEC.path
    assert row["source_revision"] == REVISION
    assert row["source_kind"] == "source-document"
    assert row["admission"] == "DISCOVERED_REVIEW_REQUIRED"
    assert row["candidate_state"] == "DISCOVERED_REVIEW_REQUIRED"
    assert row["content_access"] == "CONTROLLER_ONLY"


def test_candidate_limit_counts_eligible_sections_and_keeps_original_ids() -> None:
    sections = []
    for index in range(30):
        sections.extend([(f"Navigation {index}", "x"), (f"Details {index}", CONTENT)])
    rows = markdown_candidates(SPEC, REVISION, document(sections))

    assert len(rows) == MAX_TEXT_CANDIDATES
    assert [row["id"] for row in rows] == [
        expected_id(2 * index + 1, f"Details {index}")
        for index in range(MAX_TEXT_CANDIDATES)
    ]


def test_existing_eligible_sections_keep_order_ids_and_content_bounds() -> None:
    sections = [(f"Details {index}", CONTENT) for index in range(30)]
    sections[0] = ("Details 0", "x" * (MAX_CANDIDATE_CHARS + 200))
    rows = markdown_candidates(SPEC, REVISION, document(sections))

    assert len(rows) == MAX_TEXT_CANDIDATES
    assert [row["id"] for row in rows] == [
        expected_id(index, f"Details {index}") for index in range(MAX_TEXT_CANDIDATES)
    ]
    assert rows[0]["content"] == "x" * MAX_CANDIDATE_CHARS
    assert all(row["content"] == CONTENT for row in rows[1:])


@pytest.mark.parametrize(
    "payload", [b"", b"#\n##\n####\n", document([("Navigation", "x")] * 30)]
)
def test_no_eligible_sections_still_fail_closed(payload: bytes) -> None:
    with pytest.raises(RefreshError, match="no bounded sections found"):
        markdown_candidates(SPEC, REVISION, payload)


def test_secret_screening_covers_input_after_candidate_limit() -> None:
    sections = [(f"Details {index}", CONTENT) for index in range(MAX_TEXT_CANDIDATES)]
    sections.append(("Rejected tail", "-----BEGIN PRIVATE KEY-----"))
    with pytest.raises(RefreshError, match="secret-like material rejected"):
        markdown_candidates(SPEC, REVISION, document(sections))


@pytest.mark.parametrize("eligible_count", [23, 24, 25])
def test_exact_candidate_limit_and_minimum_content_length(eligible_count: int) -> None:
    sections = [("Too short", "x" * 39)] + [
        (f"Exact minimum {index}", "x" * 40) for index in range(eligible_count)
    ]
    rows = markdown_candidates(SPEC, REVISION, document(sections))

    assert len(rows) == min(eligible_count, MAX_TEXT_CANDIDATES)
    assert all(row["content"] == "x" * 40 for row in rows)
    assert [row["id"] for row in rows] == [
        expected_id(index + 1, f"Exact minimum {index}") for index in range(len(rows))
    ]


def test_duplicate_sections_retain_distinct_original_section_identities() -> None:
    rows = markdown_candidates(SPEC, REVISION, document([("Repeated", CONTENT)] * 30))

    assert len(rows) == MAX_TEXT_CANDIDATES
    assert [row["id"] for row in rows] == [
        expected_id(index, "Repeated") for index in range(MAX_TEXT_CANDIDATES)
    ]
    assert len({row["id"] for row in rows}) == MAX_TEXT_CANDIDATES


@pytest.mark.parametrize("prefix", [b"", document([("Details", CONTENT)] * 24)])
def test_invalid_utf8_anywhere_in_input_is_rejected(prefix: bytes) -> None:
    with pytest.raises(UnicodeDecodeError):
        markdown_candidates(SPEC, REVISION, prefix + b"\xff")
