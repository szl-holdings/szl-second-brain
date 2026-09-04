"""SZL Second Brain — governed retrieval and review-gated frontier memory.

Public surfaces return handles and digests only. Content hydration requires an
explicit principal/tenant authorizer inside a trusted controller. Continuous
learning means content-addressed public-source candidates proposed for review;
it never means silent training, automatic truth promotion, or execution. The
private 9,464-node graph is not admitted here and never enters gradients.
Lambda remains Conjecture 1.
"""
from __future__ import annotations

from second_brain.frontier import (
    AuthorizedFrontierHydrator,
    FrontierBoundaryError,
    FrontierIndex,
    anatomy_feed,
    frontier_index,
    frontier_search,
    frontier_status,
)
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

__version__ = "1.3.0"

__all__ = [
    "AuthorizedFrontierHydrator",
    "AuthorizedHydrator",
    "FrontierBoundaryError",
    "FrontierIndex",
    "HybridSecondBrain",
    "RetrievalBoundaryError",
    "SecondBrainIndex",
    "anatomy_feed",
    "frontier_index",
    "frontier_search",
    "frontier_status",
    "hybrid_context",
    "hybrid_index",
    "index",
    "navigator_context",
    "rag_status",
    "search",
    "__version__",
]
