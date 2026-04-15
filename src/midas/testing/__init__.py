"""
M20 — Testing Infrastructure.

3-tier test strategy: Tier 1 (unit), Tier 2 (integration), Tier 3 (E2E).
Shared fixtures, DataFlow test helpers, and conftest extensions.

Ref: specs/13, rules/testing.md
"""

from midas.testing.fixtures import FabricTestFixture, create_test_fabric
from midas.testing.assertions import (
    assert_pit_tuple,
    assert_fabric_row_matches,
    assert_no_future_leak,
)

__all__ = [
    "FabricTestFixture",
    "create_test_fabric",
    "assert_pit_tuple",
    "assert_fabric_row_matches",
    "assert_no_future_leak",
]
