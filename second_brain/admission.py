"""second_brain.admission — content-bound corpus admission over the HIRAG gate.

Bridges the verified public corpus generation (second_brain.corpus) to the HIRAG
admission graph (second_brain.hirag) so hybrid retrieval can gate its ranked
selection. The trust anchor is content-binding: a node is receipt-valid only
when its declared content digest was recomputed over the exact bytes AND its
source revision is the corpus generation sha256 the corpus was admitted from.

Honesty contract:
  * License values are owner declarations passed through EXACTLY (no
    normalization, no inference). An absent license becomes "unknown", which the
    gate refuses: unknown rights are not admissible (fail closed).
  * ingested_at is a REQUIRED, controller-measured timestamp. Nothing is
    fabricated: no metadata, no admission.
  * Relevance is rank-derived (1/rank), never a quality claim; the gate is a
    filter, and whether it helps is the pre-declared evaluation's question.
  * A configured gate with no declared licenses refuses everything until the
    owner declares per-node rights. That is the intended fail-closed behavior.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Any

from second_brain.corpus import Corpus
from second_brain.hirag import HIRAG, HiragError, ProvenanceDAG, EvidenceNode

SCHEMA = "szl.second-brain.corpus-admission/v1"
HIRAG_SCHEMA = "szl.hirag/v1"
RANK_DERIVED_RELEVANCE = "RANK_DERIVED_1_OVER_RANK"
UNKNOWN_LICENSE = "unknown"


class CorpusAdmissionError(ValueError):
    """The corpus admission configuration is invalid; construction fails closed."""


class CorpusAdmission:
    """A HIRAG admission gate bound to one verified corpus generation.

    Construction is all-or-nothing: the corpus file digest must equal the
    declared generation sha256, every row's content digest is recomputed, every
    node must carry owner-declared metadata (a measured ingested_at; license is
    optional and an absent license refuses at gate time), and every HiragError
    is wrapped as CorpusAdmissionError.
    """

    def __init__(self, corpus: Corpus, *, generation_sha256: str,
                 node_metadata: Mapping[str, Mapping[str, Any]],
                 tau: float = 0.5, weights: Mapping[str, float] | None = None,
                 freshness_window_s: float = 30 * 24 * 3600) -> None:
        if not isinstance(corpus, Corpus):
            raise CorpusAdmissionError("corpus must be a loaded Corpus")
        if not isinstance(generation_sha256, str) or not generation_sha256:
            raise CorpusAdmissionError("generation_sha256 is required")
        if corpus.file_sha256 != generation_sha256:
            raise CorpusAdmissionError("corpus file digest does not match the declared generation")
        if not isinstance(node_metadata, Mapping):
            raise CorpusAdmissionError("node_metadata must be a mapping of node_id to metadata")
        self.generation_sha256 = generation_sha256
        dag = ProvenanceDAG()
        licenses: dict[str, str] = {}
        for row in corpus.rows:
            # content binding, recomputed here: declared digest over exact bytes
            if hashlib.sha256(row.text.encode("utf-8")).hexdigest() != row.sha256:
                raise CorpusAdmissionError("corpus content integrity failure for node " + row.node_id)
            meta = node_metadata.get(row.node_id)
            if not isinstance(meta, Mapping):
                raise CorpusAdmissionError("missing owner metadata for node " + row.node_id)
            ingested_at = meta.get("ingested_at")
            if (not isinstance(ingested_at, (int, float)) or isinstance(ingested_at, bool)
                    or not math.isfinite(ingested_at)):
                raise CorpusAdmissionError("measured ingested_at is required for node " + row.node_id)
            license_value = meta.get("license")
            if license_value is None:
                license_value = UNKNOWN_LICENSE  # absent rights are unknown rights
            elif not isinstance(license_value, str) or not license_value.strip():
                raise CorpusAdmissionError("license must be a non-empty string for node " + row.node_id)
            licenses[row.node_id] = license_value  # passed through EXACTLY
            dag.add(EvidenceNode(node_id=row.node_id, content=row.text,
                                 receipt_hash=row.sha256, source_revision=generation_sha256,
                                 license=license_value, ingested_at=float(ingested_at), level=0))
        self._licenses = licenses
        try:
            self._hirag = HIRAG(
                dag, tau=tau, weights=dict(weights) if weights is not None else None,
                freshness_window_s=freshness_window_s,
                trust_anchor=self._content_binding_anchor)
        except HiragError as exc:
            raise CorpusAdmissionError("hirag configuration rejected: " + str(exc)) from exc

    @property
    def dag(self) -> ProvenanceDAG:
        return self._hirag.dag

    def _content_binding_anchor(self, node: EvidenceNode) -> bool:
        """Receipt axis: the node carries the verified content digest AND is
        bound to the exact corpus generation this gate was constructed over."""
        return bool(node.receipt_hash) and node.source_revision == self.generation_sha256

    def admit_selection(self, selected: Sequence[str],
                        now: float | None = None) -> dict[str, Any]:
        """Admit a ranked selection. Relevance is rank-derived (1/rank), a
        measured position signal — not a quality claim. Refused nodes are
        reported, never silently dropped."""
        if (not isinstance(selected, Sequence) or isinstance(selected, (str, bytes, bytearray))):
            raise CorpusAdmissionError("selected must be a sequence of node IDs")
        ranked: list[tuple[str, float]] = []
        for position, node_id in enumerate(selected, 1):
            if not isinstance(node_id, str):
                raise CorpusAdmissionError("node ID must be a string")
            ranked.append((node_id, 1.0 / position))
        try:
            run = self._hirag.retrieve_and_admit(ranked, now=now)
        except HiragError as exc:
            raise CorpusAdmissionError("admission run rejected: " + str(exc)) from exc
        return {**run, "schema": SCHEMA, "gate": HIRAG_SCHEMA,
                "relevance_measure": RANK_DERIVED_RELEVANCE}


__all__ = ["CorpusAdmission", "CorpusAdmissionError", "SCHEMA", "RANK_DERIVED_RELEVANCE"]
