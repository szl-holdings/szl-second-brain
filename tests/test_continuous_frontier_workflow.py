from pathlib import Path


WORKFLOW = Path(".github/workflows/continuous-frontier-memory.yml")


def test_source_test_toolchain_installs_the_project_test_extra() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    install_step = text.split("      - name: Install the source-test toolchain\n", 1)[1].split(
        "\n      - name:", 1
    )[0]

    assert '-e ".[test]"' in install_step
    assert "-r requirements.txt" not in install_step


def test_review_proposal_fails_over_to_an_explicit_external_handoff() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "pull-requests: read" in text
    assert "gh pr create" in text
    assert "BRANCH_READY_EXTERNAL_PR_REQUIRED" in text
    assert "set +e" in text
    assert "Resource not accessible by integration" in text
    assert 'exit "$pr_status"' in text


def test_write_scope_is_granted_to_the_refresh_job_not_the_workflow() -> None:
    # OpenSSF Scorecard Token-Permissions: the workflow default stays read-only and
    # the only write scope (pushing the content-addressed review branch) is job-level.
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow_level, jobs = text.split("\njobs:\n", 1)
    refresh_header = jobs.split("  refresh:\n", 1)[1].split("\n    steps:\n", 1)[0]

    assert "\npermissions:\n  contents: read\n\n" in workflow_level
    assert ": write" not in workflow_level
    assert "    permissions:\n      contents: write\n      pull-requests: read\n" in refresh_header
    assert 'git push origin "HEAD:$branch"' in jobs


def test_review_proposal_has_no_merge_or_approval_authority() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    forbidden = ("gh pr merge", "gh pr review --approve", "merge_group:")
    assert all(fragment not in text for fragment in forbidden)
