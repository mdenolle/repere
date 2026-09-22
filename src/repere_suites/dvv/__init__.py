"""dv/v processing benchmark suites for Repère (backed by codameter)."""
from __future__ import annotations

from .scorers import make_scorer_from_spec
from .suite import (
    ALL_SUITES,
    DATASET_ID,
    VERSION,
    DVVParamRecommendationSuite,
    DVVSeriesSuite,
)

__all__ = [
    "ALL_SUITES",
    "DATASET_ID",
    "VERSION",
    "DVVParamRecommendationSuite",
    "DVVSeriesSuite",
    "make_scorer_from_spec",
]
