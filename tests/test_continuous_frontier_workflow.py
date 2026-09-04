from pathlib import Path


WORKFLOW = Path(".github/workflows/continuous-frontier-memory.yml")


def test_review_proposal_fails_over_to_an_explicit_external_handoff() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "pull-requests: read" in text
    assert "gh pr create" in text
    assert "BRANCH_READY_EXTERNAL_PR_REQUIRED" in text
    assert "set +e" in text
    assert "Resource not accessible by integration" in text
    assert 'exit "$pr_status"' in text


def test_review_proposal_has_no_merge_or_approval_authority() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    forbidden = ("gh pr merge", "gh pr review --approve", "merge_group:")
    assert all(fragment not in text for fragment in forbidden)
