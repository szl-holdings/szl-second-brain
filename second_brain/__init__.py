"""SZL Second Brain — governed public retrieval and controller hydration.

The public surface returns handles and digests only. Content hydration requires
an explicit principal/tenant authorizer inside the trusted controller. The
private 9464-node graph is not admitted here and never enters gradients.
Lambda remains Conjecture 1.
"""
from __future__ import annotations

from second_brain.hybrid import (
    AuthorizedHydrator,
    HybridSecondBrain,
    RetrievalBoundaryError,
    hybrid_context,
    hybrid_index,
)
from second_brain.retrieve import (
    SecondBrainIndex,
    index,
    navigator_context,
    rag_status,
)
from second_brain.retrieve import retrieve as search

__version__ = "1.2.0"

__all__ = [
    "AuthorizedHydrator",
    "HybridSecondBrain",
    "RetrievalBoundaryError",
    "SecondBrainIndex",
    "hybrid_context",
    "hybrid_index",
    "index",
    "navigator_context",
    "rag_status",
    "search",
    "__version__",
]
