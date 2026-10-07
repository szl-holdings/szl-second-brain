# SPDX-License-Identifier: Apache-2.0
"""Bounded public research metadata; evidence discovery grants no authority.

The network entry point accepts provider identifiers, never arbitrary URLs. It
uses only the two declared HTTPS APIs, refuses redirects, and does not fetch
paper text, linked licences, repositories, or metadata-provided URLs. Captures
are versioned by canonical metadata bytes, not mislabeled as Git revisions.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Callable

SCHEMA = "szl.second-brain.public-research/v1"
MAX_RESPONSE_BYTES = 256 * 1024
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 96
MAX_AUTHORS = 32
MAX_FIELD_CHARS = 240
MAX_AGE_DAYS = 180
USER_AGENT = "SZL-SecondBrain-PublicResearch/1.0 (bounded metadata discovery)"
# Conservative public-pool pacing; response limits may still require stopping.
# https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/
_REQUEST_INTERVALS = {"arxiv": 3.0, "crossref": 1.0}
_DOI = re.compile(r"^10\.\d{4,9}/[A-Za-z0-9._;()/:-]{1,180}$")
_ARXIV = re.compile(r"^\d{4}\.\d{4,5}(?:v[1-9]\d{0,2})?$")
_ARXIV_VERSION = re.compile(r"^\d{4}\.\d{4,5}v[1-9]\d{0,2}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SECRET = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|"
    r"\b(?:sk-|gh[pousr]_|hf_)[A-Za-z0-9_-]{24,}\b|\bAKIA[0-9A-Z]{16}\b"
)
_ATOM = "{http://www.w3.org/2005/Atom}"


class ResearchBoundaryError(ValueError):
    """A public metadata input violated a bounded admission contract."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ResearchBoundaryError("duplicate JSON key")
            result[key] = value
        return result

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ResearchBoundaryError("non-finite JSON number")
        return number

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_float=finite_float,
                          parse_constant=lambda _: (_ for _ in ()).throw(ResearchBoundaryError("non-finite JSON number")))
    except ResearchBoundaryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError, OverflowError) as exc:
        raise ResearchBoundaryError("invalid metadata JSON") from exc


def clean(value: Any, *, limit: int = MAX_FIELD_CHARS) -> str:
    if not isinstance(value, str):
        raise ResearchBoundaryError("metadata field is not text")
    if _SECRET.search(value):
        raise ResearchBoundaryError("secret-like metadata rejected")
    # Metadata may contain formatting. Strip markup and reject control text;
    # instructions in titles are data, never execution or prompt authority.
    value = re.sub(r"<[^>]{0,512}>", " ", value)
    value = " ".join(value.split())
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ResearchBoundaryError("metadata control character rejected")
    if not value or len(value) > limit:
        raise ResearchBoundaryError("metadata field is empty or exceeds bound")
    return value


def identifier_url(provider: str, identifier: str) -> str:
    if not isinstance(identifier, str):
        raise ResearchBoundaryError("provider identifier must be text")
    if provider == "crossref" and _DOI.fullmatch(identifier):
        return "https://api.crossref.org/works/" + urllib.parse.quote(identifier.lower(), safe="")
    if provider == "arxiv" and _ARXIV.fullmatch(identifier):
        return "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": identifier, "max_results": 1})
    raise ResearchBoundaryError("unsupported or malformed public identifier")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        raise ResearchBoundaryError("metadata API redirect rejected")


class PublicMetadataClient:
    """Sequential requests, no retries; each provider has per-client pacing.

    The caller must ensure this is the only arXiv collector across controlled
    processes and machines. The CLI uses a local exclusive lock as an additional
    guard. Three-second arXiv and conservative one-second Crossref intervals do
    not claim that a process-local timer enforces an aggregate global limit.
    """

    def __init__(self, *, transport: Callable[[str], bytes] | None = None, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        self._transport = transport or self._request
        self._clock, self._sleep = clock, sleep
        self._last_request: dict[str, float] = {}

    @staticmethod
    def _request(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/atom+xml"})
        try:
            with urllib.request.build_opener(_NoRedirect()).open(request, timeout=20) as response:
                if response.geturl() != url or response.status != 200:
                    raise ResearchBoundaryError("metadata API origin or status changed")
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise ResearchBoundaryError("public metadata request failed") from exc
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ResearchBoundaryError("metadata response exceeds byte bound")
        return payload

    def capture(self, provider: str, identifier: str, *, observed_at: str) -> dict[str, Any]:
        url = identifier_url(provider, identifier)
        parse_timestamp(observed_at)
        if provider in self._last_request:
            delay = _REQUEST_INTERVALS[provider] - (self._clock() - self._last_request[provider])
            if delay > 0:
                self._sleep(delay)
        # Set the timer before the request: failures count towards spacing too.
        self._last_request[provider] = self._clock()
        raw = self._transport(url)
        if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
            raise ResearchBoundaryError("metadata response exceeds byte bound")
        metadata = parse_crossref(raw, identifier) if provider == "crossref" else parse_arxiv(raw, identifier)
        captured = canonical_bytes(metadata)
        return {
            "provider": provider,
            "identifier": metadata["identifier"],
            "metadata": metadata,
            "capture_sha256": digest(captured),
            "capture_base64": base64.b64encode(captured).decode("ascii"),
            "request_url": url,
            "response_sha256": digest(raw),
            "response_bytes": len(raw),
            "observed_at": observed_at,
            "source_authentication": "PUBLIC_HTTPS_METADATA_NOT_INDEPENDENT_ATTESTATION",
            "candidate_state": "DISCOVERED_REVIEW_REQUIRED",
        }


def parse_timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ResearchBoundaryError("invalid observation timestamp") from exc
    if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(result):
        raise ResearchBoundaryError("observation timestamp must be UTC")
    return result


def _date(parts: Any) -> str | None:
    if parts is None:
        return None
    try:
        fields = parts["date-parts"][0]
        if not isinstance(fields, list) or not 1 <= len(fields) <= 3:
            raise ValueError
        if any(type(field) is not int for field in fields):
            raise ValueError
        stamp = datetime(fields[0], fields[1] if len(fields) > 1 else 1, fields[2] if len(fields) > 2 else 1)
        return stamp.strftime("%Y-%m-%d")[: {1: 4, 2: 7, 3: 10}[len(fields)]]
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ResearchBoundaryError("invalid publication date") from exc


def parse_crossref(raw: bytes, requested: str) -> dict[str, Any]:
    value = strict_json(raw)
    if not isinstance(value, dict) or value.get("status") != "ok" or value.get("message-type") != "work":
        raise ResearchBoundaryError("Crossref work envelope missing")
    item = value.get("message")
    if not isinstance(item, dict) or str(item.get("DOI", "")).lower() != requested.lower():
        raise ResearchBoundaryError("Crossref DOI identity mismatch")
    titles = item.get("title")
    if not isinstance(titles, list) or len(titles) != 1:
        raise ResearchBoundaryError("Crossref title missing or ambiguous")
    authors = item.get("author", [])
    if not isinstance(authors, list) or len(authors) > MAX_AUTHORS:
        raise ResearchBoundaryError("author count exceeds bound")
    names = []
    for author in authors:
        if not isinstance(author, dict):
            raise ResearchBoundaryError("invalid author")
        name = author.get("name") or " ".join(str(author.get(key, "")) for key in ("given", "family"))
        names.append(clean(name))
    licences = item.get("license", [])
    if not isinstance(licences, list) or len(licences) > 8:
        raise ResearchBoundaryError("licence count exceeds bound")
    urls = []
    for licence in licences:
        candidate = clean(licence.get("URL", "")) if isinstance(licence, dict) else ""
        parsed = urllib.parse.urlsplit(candidate)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ResearchBoundaryError("malformed licence metadata URL")
        urls.append(candidate)
    doi = requested.lower()
    return {
        "provider": "crossref", "identifier": doi, "canonical_url": "https://doi.org/" + doi,
        "title": clean(titles[0]), "authors": names,
        "published": _date(item.get("published") or item.get("issued")),
        "updated": None, "categories": [], "licence_urls": sorted(set(urls)),
        "metadata_licence": "NOT_DECLARED_BY_RESPONSE", "full_text_licence": "NOT_INFERRED",
    }


def parse_arxiv(raw: bytes, requested: str) -> dict[str, Any]:
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", raw, re.I):
        raise ResearchBoundaryError("XML declarations rejected")
    try:
        root = ET.fromstring(raw)
    except (ET.ParseError, RecursionError) as exc:
        raise ResearchBoundaryError("invalid arXiv XML") from exc
    entries = root.findall(_ATOM + "entry")
    if root.tag != _ATOM + "feed" or len(entries) != 1:
        raise ResearchBoundaryError("arXiv must return exactly one entry")
    item = entries[0]
    identity_url = item.findtext(_ATOM + "id", "")
    match = re.fullmatch(r"https?://arxiv\.org/abs/(\d{4}\.\d{4,5}v[1-9]\d{0,2})", identity_url)
    if not match or match[1].split("v")[0] != requested.split("v")[0] or ("v" in requested and match[1] != requested):
        raise ResearchBoundaryError("arXiv version identity mismatch")
    authors = item.findall(_ATOM + "author")
    categories = item.findall(_ATOM + "category")
    if len(authors) > MAX_AUTHORS or len(categories) > 12:
        raise ResearchBoundaryError("arXiv metadata count exceeds bound")
    published, updated = item.findtext(_ATOM + "published"), item.findtext(_ATOM + "updated")
    for stamp in (published, updated):
        parse_timestamp(stamp)
    return {
        "provider": "arxiv", "identifier": match[1], "canonical_url": "https://arxiv.org/abs/" + match[1],
        "title": clean(item.findtext(_ATOM + "title", "")),
        "authors": [clean(author.findtext(_ATOM + "name", "")) for author in authors],
        "published": published, "updated": updated,
        "categories": [clean(category.get("term", "")) for category in categories],
        "licence_urls": [], "metadata_licence": "CC0-1.0", "full_text_licence": "NOT_INFERRED",
    }


def validate_snapshot(snapshot: Any, *, now: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(snapshot, dict) or snapshot.get("schema") != SCHEMA or snapshot.get("state") != "DISCOVERED_REVIEW_REQUIRED":
        raise ResearchBoundaryError("invalid research snapshot")
    if any(snapshot.get(key) != "NONE" for key in ("training_authority", "promotion_authority", "execution_authority")):
        raise ResearchBoundaryError("research snapshot grants authority")
    if len(canonical_bytes(snapshot)) > MAX_SNAPSHOT_BYTES:
        raise ResearchBoundaryError("research snapshot exceeds byte bound")
    records = snapshot.get("records")
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_RECORDS:
        raise ResearchBoundaryError("research record count exceeds bound")
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or record.get("candidate_state") != "DISCOVERED_REVIEW_REQUIRED":
            raise ResearchBoundaryError("research record authority invalid")
        try:
            captured = base64.b64decode(record["capture_base64"], validate=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchBoundaryError("research capture missing") from exc
        if len(captured) > MAX_RESPONSE_BYTES:
            raise ResearchBoundaryError("research capture exceeds byte bound")
        sha = digest(captured)
        if record.get("capture_sha256") != sha or sha in seen:
            raise ResearchBoundaryError("research capture digest mismatch or duplicate")
        seen.add(sha)
        metadata = strict_json(captured)
        if metadata != record.get("metadata") or canonical_bytes(metadata) != captured:
            raise ResearchBoundaryError("research capture projection mismatch")
        provider, identifier = record.get("provider"), record.get("identifier")
        if metadata.get("provider") != provider or metadata.get("identifier") != identifier:
            raise ResearchBoundaryError("research provider identity mismatch")
        expected_keys = {"provider", "identifier", "canonical_url", "title", "authors", "published", "updated", "categories", "licence_urls", "metadata_licence", "full_text_licence"}
        if set(metadata) != expected_keys or metadata["full_text_licence"] != "NOT_INFERRED":
            raise ResearchBoundaryError("unsupported metadata projection")
        for key, bound in (("authors", MAX_AUTHORS), ("categories", 12), ("licence_urls", 8)):
            values = metadata[key]
            if not isinstance(values, list) or len(values) > bound:
                raise ResearchBoundaryError("metadata count exceeds bound")
            for value in values:
                if clean(value) != value:
                    raise ResearchBoundaryError("metadata field is not sanitized")
        if provider == "arxiv" and not _ARXIV_VERSION.fullmatch(identifier or ""):
            raise ResearchBoundaryError("arXiv record is not version pinned")
        expected_url = "https://arxiv.org/abs/" + identifier if provider == "arxiv" else "https://doi.org/" + identifier
        if metadata["canonical_url"] != expected_url:
            raise ResearchBoundaryError("canonical source URL mismatch")
        if provider == "arxiv":
            if metadata["metadata_licence"] != "CC0-1.0":
                raise ResearchBoundaryError("arXiv metadata licence changed")
            parse_timestamp(metadata["published"])
            parse_timestamp(metadata["updated"])
        elif metadata["metadata_licence"] != "NOT_DECLARED_BY_RESPONSE" or metadata["updated"] is not None:
            raise ResearchBoundaryError("Crossref metadata licence or revision inferred")
        if provider == "crossref":
            if identifier != identifier.lower():
                raise ResearchBoundaryError("Crossref DOI is not canonical")
            publication = metadata["published"]
            if publication is not None:
                if not isinstance(publication, str) or not re.fullmatch(r"\d{4}(?:-\d{2})?(?:-\d{2})?", publication):
                    raise ResearchBoundaryError("Crossref publication date malformed")
                fields = [int(field) for field in publication.split("-")]
                _date({"date-parts": [fields]})
        request = record.get("request_url", "")
        if provider == "arxiv":
            allowed = {identifier_url(provider, identifier), identifier_url(provider, identifier.split("v")[0])}
        else:
            allowed = {identifier_url(provider, identifier)}
        if request not in allowed:
            raise ResearchBoundaryError("research request origin mismatch")
        if not _SHA256.fullmatch(str(record.get("response_sha256", ""))) or type(record.get("response_bytes")) is not int or not 0 < record["response_bytes"] <= MAX_RESPONSE_BYTES:
            raise ResearchBoundaryError("research response receipt invalid")
        stamp = parse_timestamp(record.get("observed_at"))
        if now:
            age = (parse_timestamp(now) - stamp).total_seconds()
            if age < -300 or age > MAX_AGE_DAYS * 86400:
                raise ResearchBoundaryError("research capture is future dated or stale")
        if clean(metadata.get("title")) != metadata["title"]:
            raise ResearchBoundaryError("metadata title is not sanitized")
        if record.get("source_authentication") != "PUBLIC_HTTPS_METADATA_NOT_INDEPENDENT_ATTESTATION":
            raise ResearchBoundaryError("unsupported source authentication claim")
    return records


def merge_captures(previous: dict[str, Any] | None, captures: list[dict[str, Any]]) -> dict[str, Any]:
    records = validate_snapshot(previous) if previous else []
    merged = {record["capture_sha256"]: record for record in records}
    for capture in captures:
        # Same projected bytes preserve the first capture, making reruns stable.
        merged.setdefault(capture["capture_sha256"], capture)
    result = {"schema": SCHEMA, "state": "DISCOVERED_REVIEW_REQUIRED", "records": sorted(merged.values(), key=lambda row: (row["provider"], row["identifier"], row["capture_sha256"])), "training_authority": "NONE", "promotion_authority": "NONE", "execution_authority": "NONE"}
    validate_snapshot(result)
    return result
