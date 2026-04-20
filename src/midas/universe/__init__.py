"""
M02 Universe Construction.

ETF selection, S&P 1500 filtering, holdings overlap analysis, factor gap detection,
universe changelog writer, review scheduler, and constraint enforcement.

Ref: specs/03-universe-and-data.md §1
Ref: T-02-01 through T-02-07
"""

from midas.universe.etf_selection import (
    ETFCandidate,
    FACTOR_MAP,
    detect_missing_exposures,
    score_etf,
    select_etfs,
)
from midas.universe.filters import SP1500Candidate, filter_sp1500_constituents
from midas.universe.overlap import compute_overlap, dedupe_overlapping
from midas.universe.factor_gap import FactorGap, detect_factor_gaps
from midas.universe.changelog import get_changelog, record_addition, record_removal
from midas.universe.scheduler import ReviewSchedule, compute_next_review_dates
from midas.universe.constraints import UniverseConstraint

__all__ = [
    # ETF selection
    "ETFCandidate",
    "FACTOR_MAP",
    "score_etf",
    "select_etfs",
    "detect_missing_exposures",
    # S&P 1500 filtering
    "SP1500Candidate",
    "filter_sp1500_constituents",
    # Overlap analysis
    "compute_overlap",
    "dedupe_overlapping",
    # Factor gap
    "FactorGap",
    "detect_factor_gaps",
    # Changelog
    "record_addition",
    "record_removal",
    "get_changelog",
    # Scheduler
    "ReviewSchedule",
    "compute_next_review_dates",
    # Constraints
    "UniverseConstraint",
]
