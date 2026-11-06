"""The Space publish include must contain every Dockerfile COPY source.

SZLHOLDINGS/szl-second-brain at Hub SHA 2f4d88d74451 was an 8-file stub.
Its Dockerfile still copied train/training_receipt.json, train/eval_report.json,
second_brain/, data/, and static/, and the Space stayed in BUILD_ERROR.
A full-checkout docker build does not catch that omission.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_space_payload", ROOT / "tools" / "check_space_payload.py"
)
checker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(checker)

# Live Space siblings at 2f4d88d744510410c9343bf9cb8e25c6f33c0ba5.
HUB_STUB = {
    ".gitattributes",
    "Dockerfile",
    "LICENSE",
    "README.md",
    "app.py",
    "app_operational.py",
    "app_refinement.py",
    "requirements.txt",
}


def test_committed_manifest_covers_every_dockerfile_copy_source() -> None:
    include = checker.evaluate(ROOT)
    assert "train/training_receipt.json" in include
    assert "train/eval_report.json" in include
    assert any(path.startswith("second_brain/") for path in include)
    assert any(path.startswith("data/") for path in include)
    assert any(path.startswith("static/") for path in include)
    assert "train/train.jsonl" not in include
    assert "train/build_curriculum.py" not in include
    assert "train/gate_abstain.jsonl" not in include


def test_observed_hub_stub_omits_the_copy_sources_that_broke_the_build() -> None:
    files = checker.tracked_files(ROOT)
    required = checker.required_payload((ROOT / "Dockerfile").read_text(encoding="utf-8"), files)
    missing, _extra = checker.coverage_gap(required, HUB_STUB)
    assert "train/training_receipt.json" in missing
    assert "train/eval_report.json" in missing
    assert any(path.startswith("second_brain/") for path in missing)
    assert any(path.startswith("data/") for path in missing)
    assert any(path.startswith("static/") for path in missing)
    assert "app.py" not in missing
    assert "requirements.txt" not in missing


def test_dropping_a_copy_source_from_the_include_fails() -> None:
    files = checker.tracked_files(ROOT)
    required = checker.required_payload((ROOT / "Dockerfile").read_text(encoding="utf-8"), files)
    thinned = set(required)
    thinned.remove("train/training_receipt.json")
    missing, _extra = checker.coverage_gap(required, thinned)
    assert missing == {"train/training_receipt.json"}


def test_directory_and_multifile_copy_expand_to_tracked_files() -> None:
    files = checker.tracked_files(ROOT)
    sources = checker.parse_copy_sources((ROOT / "Dockerfile").read_text(encoding="utf-8"))
    assert "train/training_receipt.json" in sources
    assert "train/eval_report.json" in sources
    assert "second_brain/" in sources
    assert "data/" in sources
    assert "static/" in sources
    assert "app.py" in sources and "LICENSE" in sources
    expanded = checker.expand_source("second_brain/", files)
    assert expanded
    assert all(path.startswith("second_brain/") for path in expanded)
    assert checker.expand_source("train/training_receipt.json", files) == {"train/training_receipt.json"}


def test_whole_context_copy_and_stage_copies_are_rejected() -> None:
    try:
        checker.parse_copy_sources("COPY . /app\n")
    except checker.PayloadError as exc:
        assert "bare COPY" in str(exc)
    else:
        raise AssertionError("bare COPY . must fail")
    assert checker.parse_copy_sources("COPY --from=build /out/app.py /app/app.py\n") == []


def test_staged_payload_contains_each_copy_source_and_nothing_else() -> None:
    include = checker.evaluate(ROOT)
    with tempfile.TemporaryDirectory() as raw:
        destination = Path(raw) / "payload"
        checker.stage_payload(ROOT, destination, include)
        staged = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}
        assert staged == include
        assert (destination / "train" / "training_receipt.json").is_file()
        assert (destination / "train" / "eval_report.json").is_file()
        assert (destination / "second_brain" / "__init__.py").is_file()
        assert not (destination / "train" / "train.jsonl").exists()
        assert not (destination / "tests").exists()


def test_container_job_builds_the_staged_payload_not_the_full_checkout() -> None:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'tools/check_space_payload.py --stage "$RUNNER_TEMP/space-payload"' in text
    assert 'docker build --tag szl-second-brain:ci "$RUNNER_TEMP/space-payload"' in text
    assert "docker build --tag szl-second-brain:ci ." not in text
    assert "python tools/check_space_payload.py" in text


def test_readme_card_can_be_uploaded_without_rewriting_it() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    checker.validate_card(readme, dockerfile)
    description = checker.card_fields(readme)["short_description"]
    assert "continuous" in description
    assert len(description) <= checker.CARD_DESCRIPTION_LIMIT
