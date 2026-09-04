#!/usr/bin/env python3
"""Refresh the review-gated Second Brain frontier candidate corpus.

Only a fixed set of public, source-owned files is admitted. Each source is resolved
to the latest exact commit that changed that path, then fetched from immutable raw
GitHub. The output is deterministic and review-required: it never merges, trains,
publishes weights, or grants action authority.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = ROOT / "data" / "frontier-candidates.public.jsonl"
DEFAULT_STATE = ROOT / "data" / "frontier-state.v1.json"
USER_AGENT = "szl-second-brain-frontier-refresh/1.0"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_CANDIDATE_CHARS = 1_600
MAX_TEXT_CANDIDATES = 24


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    repository: str
    path: str
    parser: str


SOURCES = (
    SourceSpec(
        "formula_quant_atlas",
        "szl-holdings/szl-formulas",
        "atlas/formula-atlas.v1.json",
        "formula_atlas",
    ),
    SourceSpec(
        "ouroboros_runtime",
        "szl-holdings/szl-ouroboros",
        "README.md",
        "markdown",
    ),
    SourceSpec(
        "governed_kernel_suite",
        "szl-holdings/szl-kernels",
        "README.md",
        "markdown",
    ),
    SourceSpec(
        "living_anatomy",
        "szl-holdings/anatomy",
        "README.md",
        "markdown",
    ),
    SourceSpec(
        "a11oy_public_estate",
        "szl-holdings/a11oy",
        "governance/public-estate.v1.json",
        "public_estate",
    ),
    SourceSpec(
        "forge_production_controller",
        "szl-holdings/szl-forge",
        "inference/production.py",
        "python_contract",
    ),
    SourceSpec(
        "nemo_witness",
        "szl-holdings/szl-nemo",
        "README.md",
        "markdown",
    ),
)

_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")


class RefreshError(RuntimeError):
    """A source or generated candidate violated the refresh contract."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def request_bytes(url: str, *, token: str | None = None, limit: int) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json, application/json, text/plain;q=0.9, */*;q=0.8",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = response.read(limit + 1)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise RefreshError(f"fetch failed: {type(exc).__name__}") from exc
    if len(payload) > limit:
        raise RefreshError(f"source exceeded {limit} bytes")
    return payload


def _github_json(url: str, token: str | None) -> Any:
    try:
        raw = request_bytes(url, token=token, limit=512 * 1024)
    except RefreshError:
        if not token:
            raise
        raw = request_bytes(url, token=None, limit=512 * 1024)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RefreshError("GitHub returned invalid JSON") from exc


def resolve_path_revision(
    spec: SourceSpec,
    *,
    token: str | None,
    api_url: str = "https://api.github.com",
) -> str:
    path = urllib.parse.quote(spec.path, safe="")
    url = (
        f"{api_url.rstrip('/')}/repos/{spec.repository}/commits"
        f"?path={path}&sha=main&per_page=1"
    )
    payload = _github_json(url, token)
    if not isinstance(payload, list) or len(payload) != 1:
        raise RefreshError(f"no path revision found for {spec.source_id}")
    revision = str(payload[0].get("sha") or "").lower()
    if not _HEX_40.fullmatch(revision):
        raise RefreshError(f"invalid path revision for {spec.source_id}")
    return revision


def fetch_source(
    spec: SourceSpec,
    *,
    token: str | None,
    api_url: str = "https://api.github.com",
    raw_url: str = "https://raw.githubusercontent.com",
) -> tuple[str, bytes]:
    revision = resolve_path_revision(spec, token=token, api_url=api_url)
    encoded_path = "/".join(
        urllib.parse.quote(part, safe="") for part in spec.path.split("/")
    )
    url = f"{raw_url.rstrip('/')}/{spec.repository}/{revision}/{encoded_path}"
    payload = request_bytes(url, limit=MAX_SOURCE_BYTES)
    return revision, payload


def reject_secrets(value: str, *, source_id: str) -> None:
    for pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            raise RefreshError(f"secret-like material rejected from {source_id}")


def clean_text(value: Any, *, limit: int = MAX_CANDIDATE_CHARS) -> str:
    text = str(value or "").replace("\x00", " ").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]


def candidate_id(spec: SourceSpec, source_kind: str, stable_key: str) -> str:
    digest = hashlib.sha256(
        "\x00".join(
            (spec.repository, spec.path, source_kind, stable_key)
        ).encode("utf-8")
    ).hexdigest()
    return f"frontier:{digest[:32]}"


def make_candidate(
    spec: SourceSpec,
    revision: str,
    *,
    stable_key: str,
    title: str,
    content: str,
    source_kind: str,
    admission: str = "DISCOVERED_REVIEW_REQUIRED",
    quant_domain: str | None = None,
) -> dict[str, Any]:
    clean = clean_text(content)
    if not clean:
        raise RefreshError(f"empty generated candidate: {stable_key}")
    reject_secrets(clean, source_id=spec.source_id)
    row: dict[str, Any] = {
        "schema": "szl.second-brain.frontier-candidate/v1",
        "id": candidate_id(spec, source_kind, stable_key),
        "title": clean_text(title, limit=180),
        "content": clean,
        "content_sha256": sha256_bytes(clean.encode("utf-8")),
        "source_repository": spec.repository,
        "source_revision": revision,
        "source_path": spec.path,
        "source_kind": source_kind,
        "admission": admission,
        "candidate_state": "DISCOVERED_REVIEW_REQUIRED",
        "content_access": "CONTROLLER_ONLY",
    }
    if quant_domain:
        row["quant_domain"] = quant_domain
    return row


def formula_candidates(
    spec: SourceSpec, revision: str, payload: bytes
) -> list[dict[str, Any]]:
    value = json.loads(payload)
    if value.get("schema") != "szl.formula-quant-atlas/v1":
        raise RefreshError("formula atlas schema mismatch")
    authority = value.get("authority")
    attributed = value.get("attributed_formulas")
    executable = value.get("executable_formulas")
    domains = value.get("quant_domains")
    if not isinstance(authority, dict):
        raise RefreshError("formula authority is missing")
    if not isinstance(attributed, list) or len(attributed) != 30:
        raise RefreshError("formula atlas must expose 30 attributed records")
    if not isinstance(executable, list) or len(executable) != 21:
        raise RefreshError("formula atlas must expose 21 executable formulas")
    if not isinstance(domains, list) or len(domains) != 9:
        raise RefreshError("formula atlas must expose nine quant domains")
    if authority.get("locked_proven_count") != 8:
        raise RefreshError("locked-proven formula count drifted")
    if authority.get("lambda_status") != "CONJECTURE_1_OPEN_ADVISORY_ONLY":
        raise RefreshError("Lambda honesty boundary drifted")

    rows: list[dict[str, Any]] = []
    rows.append(
        make_candidate(
            spec,
            revision,
            stable_key="authority",
            title="SZL formula authority and proof boundary",
            content=json.dumps(authority, ensure_ascii=False, sort_keys=True),
            source_kind="formula-authority",
            admission="REFERENCE_AND_CONSTRAINT_INPUT_ONLY",
        )
    )
    for formula in attributed:
        formula_id = str(formula.get("id") or "")
        domain = str(formula.get("quant_domain") or "")
        content = "\n".join(
            (
                f"Formula: {formula_id}",
                f"Source attribution: {formula.get('source')}",
                f"Statement: {formula.get('statement')}",
                f"Class: {formula.get('class')}",
                f"Reported status: {formula.get('reported_status')}",
                f"Quant domain: {domain}",
                f"Admission: {formula.get('admission')}",
                "Locked-proof membership: UNKNOWN_NOT_INFERRED_FROM_REPORTED_STATUS",
            )
        )
        rows.append(
            make_candidate(
                spec,
                revision,
                stable_key=f"attributed:{formula_id}",
                title=f"Attributed formula · {formula_id}",
                content=content,
                source_kind="attributed-formula",
                admission=str(formula.get("admission") or "DISCOVERED_REVIEW_REQUIRED"),
                quant_domain=domain or None,
            )
        )
    for formula in executable:
        name = str(formula.get("name") or "")
        rows.append(
            make_candidate(
                spec,
                revision,
                stable_key=f"executable:{name}",
                title=f"Executable formula · {name}",
                content=(
                    f"Executable registry name: {name}\n"
                    f"Per-obligation proof status: {formula.get('proof_status')}\n"
                    "Registry membership does not infer an F-number mapping or locked proof."
                ),
                source_kind="executable-formula",
                admission="EXECUTABLE_CONSTRAINT_REVIEW_REQUIRED",
            )
        )
    for domain in domains:
        domain_id = str(domain.get("id") or "")
        rows.append(
            make_candidate(
                spec,
                revision,
                stable_key=f"domain:{domain_id}",
                title=f"Quant domain · {domain_id}",
                content=json.dumps(domain, ensure_ascii=False, sort_keys=True),
                source_kind="quant-domain",
                admission="REFERENCE_AND_CONSTRAINT_INPUT_ONLY",
                quant_domain=domain_id,
            )
        )
    return rows


def markdown_candidates(
    spec: SourceSpec, revision: str, payload: bytes
) -> list[dict[str, Any]]:
    text = payload.decode("utf-8")
    reject_secrets(text, source_id=spec.source_id)
    sections: list[tuple[str, list[str]]] = []
    current_title = spec.source_id.replace("_", " ").title()
    current: list[str] = []
    for line in text.splitlines():
        heading = re.match(r"^#{1,4}\s+(.+?)\s*$", line)
        if heading:
            if current:
                sections.append((current_title, current))
            current_title = heading.group(1).strip()
            current = []
        else:
            current.append(line)
    if current:
        sections.append((current_title, current))

    rows: list[dict[str, Any]] = []
    for index, (title, lines) in enumerate(sections[:MAX_TEXT_CANDIDATES]):
        content = clean_text("\n".join(lines))
        if len(content) < 40:
            continue
        rows.append(
            make_candidate(
                spec,
                revision,
                stable_key=f"section:{index}:{title}",
                title=f"{spec.source_id.replace('_', ' ').title()} · {title}",
                content=content,
                source_kind="source-document",
            )
        )
    if not rows:
        raise RefreshError(f"no bounded sections found for {spec.source_id}")
    return rows


def public_estate_candidates(
    spec: SourceSpec, revision: str, payload: bytes
) -> list[dict[str, Any]]:
    value = json.loads(payload)
    if value.get("schema") != "szl.public-estate/v1":
        raise RefreshError("public estate schema mismatch")
    rows = [
        make_candidate(
            spec,
            revision,
            stable_key="estate-authority",
            title="A11oy public estate authority",
            content=json.dumps(
                {
                    "estate": value.get("estate"),
                    "truth_policy": value.get("truth_policy"),
                    "platform_count": value.get("platform_count"),
                    "public_vertical_product_count": value.get(
                        "public_vertical_product_count"
                    ),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            source_kind="estate-authority",
            admission="REFERENCE_ONLY_NO_PROVIDER_MUTATION",
        )
    ]
    for group in ("platforms", "public_products"):
        items = value.get(group)
        if not isinstance(items, list):
            raise RefreshError(f"public estate {group} is not a list")
        for item in items:
            item_id = str(item.get("id") or "")
            rows.append(
                make_candidate(
                    spec,
                    revision,
                    stable_key=f"{group}:{item_id}",
                    title=f"Public estate · {item.get('title') or item_id}",
                    content=json.dumps(item, ensure_ascii=False, sort_keys=True),
                    source_kind="estate-surface",
                    admission="REFERENCE_ONLY_NO_PROVIDER_MUTATION",
                )
            )
    return rows


def python_contract_candidates(
    spec: SourceSpec, revision: str, payload: bytes
) -> list[dict[str, Any]]:
    text = payload.decode("utf-8")
    reject_secrets(text, source_id=spec.source_id)
    tree = ast.parse(text)
    rows: list[dict[str, Any]] = []
    module_doc = ast.get_docstring(tree, clean=True)
    if module_doc:
        rows.append(
            make_candidate(
                spec,
                revision,
                stable_key="module-contract",
                title="Forge production controller contract",
                content=module_doc,
                source_kind="python-contract",
                admission="REFERENCE_ONLY_EXECUTION_AUTHORITY_NONE",
            )
        )
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        doc = ast.get_docstring(node, clean=True)
        if not doc:
            continue
        if isinstance(node, ast.ClassDef):
            signature = f"class {node.name}"
        else:
            arguments = [argument.arg for argument in node.args.args]
            signature = f"def {node.name}({', '.join(arguments)})"
        rows.append(
            make_candidate(
                spec,
                revision,
                stable_key=f"symbol:{node.name}",
                title=f"Forge contract · {node.name}",
                content=f"{signature}\n\n{doc}",
                source_kind="python-contract",
                admission="REFERENCE_ONLY_EXECUTION_AUTHORITY_NONE",
            )
        )
        if len(rows) >= MAX_TEXT_CANDIDATES:
            break
    if not rows:
        raise RefreshError("Forge production controller exposed no documented contract")
    return rows


PARSERS: dict[str, Callable[[SourceSpec, str, bytes], list[dict[str, Any]]]] = {
    "formula_atlas": formula_candidates,
    "markdown": markdown_candidates,
    "public_estate": public_estate_candidates,
    "python_contract": python_contract_candidates,
}


def build_snapshot(
    source_fetcher: Callable[[SourceSpec], tuple[str, bytes]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    source_receipts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for spec in SOURCES:
        revision, payload = source_fetcher(spec)
        if not _HEX_40.fullmatch(revision):
            raise RefreshError(f"source revision is not exact: {spec.source_id}")
        text = payload.decode("utf-8")
        reject_secrets(text, source_id=spec.source_id)
        parser = PARSERS[spec.parser]
        rows = parser(spec, revision, payload)
        for row in rows:
            if row["id"] in seen_ids:
                raise RefreshError(f"duplicate candidate id: {row['id']}")
            seen_ids.add(row["id"])
        all_rows.extend(rows)
        source_receipts.append(
            {
                "source_id": spec.source_id,
                "repository": spec.repository,
                "revision": revision,
                "path": spec.path,
                "parser": spec.parser,
                "content_sha256": sha256_bytes(payload),
                "candidate_count": len(rows),
            }
        )

    all_rows.sort(key=lambda row: row["id"])
    source_receipts.sort(key=lambda row: row["source_id"])
    candidate_bytes = b"".join(canonical_bytes(row) + b"\n" for row in all_rows)
    kind_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    for row in all_rows:
        kind = str(row["source_kind"])
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        domain = row.get("quant_domain")
        if domain:
            key = str(domain)
            domain_counts[key] = domain_counts.get(key, 0) + 1
    state_core: dict[str, Any] = {
        "schema": "szl.second-brain.frontier-state/v1",
        "state": "REVIEW_REQUIRED",
        "candidate_count": len(all_rows),
        "candidate_set_sha256": sha256_bytes(candidate_bytes),
        "source_count": len(source_receipts),
        "sources": source_receipts,
        "source_kind_counts": dict(sorted(kind_counts.items())),
        "quant_domain_counts": dict(sorted(domain_counts.items())),
        "public_content_access": "HANDLES_ONLY",
        "controller_content_access": "AUTHORIZED_CONTROLLER_ONLY",
        "private_graph_nodes_loaded": 0,
        "raw_graph_nodes_admitted_to_gradients": 0,
        "training_authority": "NONE",
        "promotion_authority": "NONE",
        "execution_authority": "NONE",
        "merge_authority": "NONE",
        "lambda": "CONJECTURE_1",
        "learning_definition": (
            "Content-addressed public-source candidates are proposed for human review. "
            "No silent weight update or automatic truth promotion occurs."
        ),
    }
    state_core["state_sha256"] = sha256_bytes(canonical_bytes(state_core))
    return all_rows, state_core


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def write_snapshot(
    rows: Iterable[dict[str, Any]],
    state: dict[str, Any],
    *,
    candidates_path: Path,
    state_path: Path,
) -> None:
    candidate_payload = b"".join(canonical_bytes(row) + b"\n" for row in rows)
    state_payload = (
        json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    atomic_write(candidates_path, candidate_payload)
    atomic_write(state_path, state_payload)


def environment_token() -> str | None:
    for key in ("GH_READ_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


def fixture_fetcher(directory: Path) -> Callable[[SourceSpec], tuple[str, bytes]]:
    def fetch(spec: SourceSpec) -> tuple[str, bytes]:
        meta = json.loads(
            (directory / f"{spec.source_id}.source.json").read_text(encoding="utf-8")
        )
        payload = (directory / f"{spec.source_id}.payload").read_bytes()
        return str(meta["revision"]), payload

    return fetch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--fixture-dir", type=Path)
    parser.add_argument(
        "--api-url",
        default=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
    )
    parser.add_argument("--raw-url", default="https://raw.githubusercontent.com")
    args = parser.parse_args()

    if args.fixture_dir:
        fetcher = fixture_fetcher(args.fixture_dir)
    else:
        token = environment_token()

        def fetcher(spec: SourceSpec) -> tuple[str, bytes]:
            return fetch_source(
                spec,
                token=token,
                api_url=args.api_url,
                raw_url=args.raw_url,
            )

    rows, state = build_snapshot(fetcher)
    write_snapshot(
        rows,
        state,
        candidates_path=args.candidates,
        state_path=args.state,
    )
    print(
        json.dumps(
            {
                "state": state["state"],
                "candidate_count": state["candidate_count"],
                "candidate_set_sha256": state["candidate_set_sha256"],
                "source_count": state["source_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
