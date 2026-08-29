"""SZL second brain — public retrieval index. Not model weights.

Λ = Conjecture 1. Private 9464-node graph is not admitted here.
"""
from __future__ import annotations

from second_brain.retrieve import (
    SecondBrainIndex,
    index,
    navigator_context,
    rag_status,
)
from second_brain.retrieve import retrieve as search

__version__ = "1.0.0"

__all__ = [
    "SecondBrainIndex",
    "index",
    "navigator_context",
    "rag_status",
    "search",
    "__version__",
]
