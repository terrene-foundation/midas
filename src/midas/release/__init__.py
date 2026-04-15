"""
M21 — Release & CI/CD Infrastructure.

Version management, changelog generation, and release automation.

Ref: specs/14
"""

from midas.release.version import get_version, validate_version_consistency
from midas.release.changelog import ChangelogGenerator

__all__ = [
    "get_version",
    "validate_version_consistency",
    "ChangelogGenerator",
]
