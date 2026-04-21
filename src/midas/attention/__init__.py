"""Midas attention -- regime-adaptive disclosure and fatigue tracking.

Tracks user attention load to modulate brief density, notification
frequency, and autonomy-suggestion behavior.  Per specs/09 S3, the
budget is consumed by decisions, not by browsing.
"""

from midas.attention.budget_tracker import AttentionBudget, AttentionBudgetTracker

__all__ = [
    "AttentionBudget",
    "AttentionBudgetTracker",
]
