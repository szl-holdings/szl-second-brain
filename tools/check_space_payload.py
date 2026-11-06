#!/usr/bin/env python3
"""Fail when the Space publish include omits a Dockerfile COPY source.

The Hugging Face Space is built from the files that were actually uploaded.
``docker build`` of a full Git checkout stays green when that upload set is a
thinner stub, which is how SZLHOLDINGS/szl-second-brain reached BUILD_ERROR on
``COPY train/training_receipt.json`` while those files still existed in Git.

This gate compares the Dockerfile COPY closure to
``publishing/space-payload.manifest.json``. It does not publish, upload, or
read a Hugging Face token.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

SCHEMA = "szl.second-brain.space-payload/v1"
SOURCE_REPOSITORY = "szl-holdings/szl-second-brain"
TARGET_SPACE = "SZLHOLDINGS/szl-second-brain"
MANIFEST_PATH = Path("publishing") / "space-payload.manifest.json"
SPACE_METADATA = frozenset({"Dockerfile", "README.md"})
CARD_DESCRIPTION_LIMIT = 60
ALLOWED_KEYS = frozenset({
    "schema",
    "source_repository",
    "target_space",
    "publish",
    "doctrine",
    "include",
})


class PayloadError(Exception):
    """The publish include and the Dockerfile COPY closure disagree."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def strict_json(raw: bytes) -> object:
    def pairs(seq: list[tuple[object, object]]) -> dict[object, object]:
        keys = [key for key, _value in seq]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate JSON key")
        return dict(seq)

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PayloadError(f"space payload manifest is not strict JSON: {exc}") from exc


def tracked_files(root: Path) -> set[str]:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(root), "ls-files", "-z"],
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PayloadError(f"git ls-files failed: {exc}") from exc
    return {item.decode("utf-8") for item in output.split(b"\0") if item}


def _logical_lines(dockerfile_text: str) -> list[str]:
    logical: list[str] = []
    buffer = ""
    for raw in dockerfile_text.splitlines():
        stripped = raw.strip()
        if not buffer and (stripped.startswith("#") or stripped == ""):
            continue
        if raw.rstrip().endswith("\\"):
            buffer += raw.rstrip()[:-1] + " "
            continue
        buffer += raw
        logical.append(buffer)
        buffer = ""
    if buffer:
        logical.append(buffer)
    return logical


def parse_copy_sources(dockerfile_text: str) -> list[str]:
    """Return build-context COPY/ADD sources in Dockerfile order.

    ``COPY --from`` and remote ``ADD`` inputs are not repository files.
    A bare ``COPY .`` / ``ADD .`` is rejected: the Space payload is an
    explicit include, not the whole checkout.
    """
    sources: list[str] = []
    seen: set[str] = set()
    for line in _logical_lines(dockerfile_text):
        match_kind = line.strip().split(None, 1)
        if len(match_kind) != 2 or match_kind[0].upper() not in {"COPY", "ADD"}:
            continue
        instruction, rest = match_kind[0].upper(), match_kind[1].strip()
        if rest.startswith("["):
            try:
                array = json.loads(rest)
            except json.JSONDecodeError as exc:
                raise PayloadError(f"malformed JSON-form {instruction}: {line.strip()}") from exc
            if not isinstance(array, list) or len(array) < 2 or not all(isinstance(item, str) for item in array):
                raise PayloadError(f"invalid JSON-form {instruction}: {line.strip()}")
            context_sources = array[:-1]
        else:
            skip = False
            tokens: list[str] = []
            for token in rest.split():
                if token.startswith("--"):
                    if token.lower().startswith("--from"):
                        skip = True
                    continue
                tokens.append(token)
            if skip:
                continue
            if len(tokens) < 2:
                raise PayloadError(f"{instruction} has no source and destination: {line.strip()}")
            context_sources = tokens[:-1]
        if instruction == "ADD":
            context_sources = [source for source in context_sources if not _remote_add(source)]
        for source in context_sources:
            normalized = _normalize_source(source)
            if normalized not in seen:
                seen.add(normalized)
                sources.append(normalized)
    return sources


def _remote_add(source: str) -> bool:
    value = source.strip()
    lowered = value.lower()
    return lowered.startswith(("http://", "https://", "git://")) or (
        "@" in value and ":" in value and "://" not in value
    )


def _normalize_source(source: str) -> str:
    normalized = source.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized in {"", "."}:
        raise PayloadError("bare COPY/ADD of '.' is forbidden; list explicit payload paths")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        raise PayloadError(f"COPY source escapes the build context: {source}")
    return normalized


def expand_source(source: str, files: set[str]) -> set[str]:
    """Expand one COPY source to tracked file paths."""
    normalized = source.rstrip("/")
    if any(char in normalized for char in "*?["):
        matched = {path for path in files if fnmatch.fnmatch(path, normalized)}
        if not matched:
            raise PayloadError(f"COPY glob matches no tracked file: {source}")
        return matched
    if not source.endswith("/") and normalized in files:
        return {normalized}
    members = {path for path in files if path.startswith(normalized + "/")}
    if members:
        return members
    raise PayloadError(f"COPY source is not a tracked file or directory: {source}")


def required_payload(dockerfile_text: str, files: set[str]) -> set[str]:
    required: set[str] = set()
    for source in parse_copy_sources(dockerfile_text):
        required.update(expand_source(source, files))
    missing_metadata = SPACE_METADATA - files
    if missing_metadata:
        raise PayloadError("tracked Space metadata missing: " + ", ".join(sorted(missing_metadata)))
    return required | set(SPACE_METADATA)


def exposed_port(dockerfile_text: str) -> str:
    ports = []
    for line in dockerfile_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.upper().startswith("EXPOSE "):
            parts = stripped.split()
            if len(parts) != 2:
                raise PayloadError(f"EXPOSE must name one port: {stripped}")
            ports.append(parts[1])
    if ports != ["7860"]:
        raise PayloadError(f"Dockerfile must EXPOSE 7860 exactly once, found {ports}")
    return ports[0]


def card_fields(readme_text: str) -> dict[str, str]:
    if not readme_text.startswith("---\n"):
        raise PayloadError("README.md has no Space card front matter")
    end = readme_text.find("\n---", 4)
    if end < 0:
        raise PayloadError("README.md Space card front matter is not closed")
    fields: dict[str, str] = {}
    for line in readme_text[4:end].splitlines():
        if not line.strip() or line[:1] in {" ", "\t", "-"} or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip("'").strip('"')
    return fields


def validate_card(readme_text: str, dockerfile_text: str) -> None:
    fields = card_fields(readme_text)
    if fields.get("sdk") != "docker":
        raise PayloadError("README Space card must set sdk: docker")
    if fields.get("app_port") != exposed_port(dockerfile_text):
        raise PayloadError("README app_port must match Dockerfile EXPOSE 7860")
    description = fields.get("short_description", "")
    if not description or len(description) > CARD_DESCRIPTION_LIMIT:
        raise PayloadError(
            "README short_description must be 1.."
            f"{CARD_DESCRIPTION_LIMIT} characters so a publisher can upload it "
            f"verbatim (found {len(description)})"
        )


def load_manifest(root: Path) -> dict[str, object]:
    path = root / MANIFEST_PATH
    if not path.is_file():
        raise PayloadError(
            f"{MANIFEST_PATH.as_posix()} is missing; Dockerfile COPY sources have no publish include"
        )
    parsed = strict_json(path.read_bytes())
    if not isinstance(parsed, dict):
        raise PayloadError("space payload manifest must be a JSON object")
    unknown = set(parsed) - ALLOWED_KEYS
    if unknown:
        raise PayloadError("unknown space payload manifest keys: " + ", ".join(sorted(unknown)))
    if parsed.get("schema") != SCHEMA:
        raise PayloadError(f"space payload schema must be {SCHEMA}")
    if parsed.get("source_repository") != SOURCE_REPOSITORY:
        raise PayloadError(f"source_repository must be {SOURCE_REPOSITORY}")
    if parsed.get("target_space") != TARGET_SPACE:
        raise PayloadError(f"target_space must be {TARGET_SPACE}")
    if parsed.get("publish") is not False:
        raise PayloadError("space payload manifest publish must be false; this file does not publish")
    include = parsed.get("include")
    if not isinstance(include, list) or not include or not all(isinstance(item, str) for item in include):
        raise PayloadError("space payload include must be a non-empty list of paths")
    if list(include) != sorted(include):
        raise PayloadError("space payload include must be sorted")
    if len(include) != len(set(include)):
        raise PayloadError("space payload include contains duplicate paths")
    for item in include:
        if item != item.strip() or "\\" in item or item.startswith("/") or item.endswith("/"):
            raise PayloadError(f"include path must be a relative file: {item}")
        if ".." in item.split("/"):
            raise PayloadError(f"include path escapes the repository: {item}")
    return parsed


def coverage_gap(required: set[str], include: set[str]) -> tuple[set[str], set[str]]:
    return required - include, include - required


def evaluate(root: Path) -> set[str]:
    files = tracked_files(root)
    dockerfile_text = (root / "Dockerfile").read_text(encoding="utf-8")
    readme_text = (root / "README.md").read_text(encoding="utf-8")
    validate_card(readme_text, dockerfile_text)
    required = required_payload(dockerfile_text, files)
    manifest = load_manifest(root)
    include = set(manifest["include"])
    untracked = include - files
    if untracked:
        raise PayloadError(
            "publish include names files that are not tracked: " + ", ".join(sorted(untracked))
        )
    missing, extra = coverage_gap(required, include)
    if missing or extra:
        parts = []
        if missing:
            parts.append("missing COPY sources: " + ", ".join(sorted(missing)))
        if extra:
            parts.append("include is outside the COPY closure: " + ", ".join(sorted(extra)))
        raise PayloadError("; ".join(parts))
    return include


def stage_payload(root: Path, destination: Path, include: set[str]) -> None:
    if destination.exists():
        raise PayloadError(f"refusing to stage into an existing directory: {destination}")
    root_resolved = root.resolve()
    for relative in sorted(include):
        source = (root / relative).resolve()
        if root_resolved not in source.parents or not source.is_file():
            raise PayloadError(f"refusing to stage a path outside the tracked file set: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        type=Path,
        help="copy the admitted payload here so docker build can use that context",
    )
    args = parser.parse_args(argv)
    try:
        include = evaluate(repo_root())
        if args.stage is not None:
            stage_payload(repo_root(), args.stage, include)
            print(f"staged {len(include)} Space payload files at {args.stage}")
        else:
            print(f"Space payload include covers {len(include)} Dockerfile COPY files")
    except PayloadError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
