"""
Custom test assertions for Midas fabric data.

Provides PIT tuple validation, row matching, and future-leak detection
for use across all test tiers.

Ref: specs/03 §2.2 (PIT discipline)
"""

from typing import Any


def assert_pit_tuple(
    row: dict[str, Any],
    require_filed_at: bool = True,
) -> None:
    """Assert that a fabric row has a valid PIT tuple.

    Every time-varying attribute should carry:
    (period_end, filed_at, restated_at, source_vintage)

    Parameters
    ----------
    row:
        The fabric row to validate.
    require_filed_at:
        If True, filed_at must be non-empty.

    Raises
    ------
    AssertionError
        If PIT fields are missing or malformed.
    """
    assert "period_end" in row, f"Missing period_end in row: {list(row.keys())}"

    if require_filed_at:
        assert "filed_at" in row, f"Missing filed_at in row: {list(row.keys())}"
        assert row["filed_at"], "filed_at must be non-empty"

    # restated_at can be empty (never restated) but must exist
    assert "restated_at" in row, f"Missing restated_at in row: {list(row.keys())}"

    # source_vintage should exist for traceability
    assert "source_vintage" in row, f"Missing source_vintage in row: {list(row.keys())}"


def assert_fabric_row_matches(
    actual: dict[str, Any],
    expected: dict[str, Any],
    ignore_fields: set[str] | None = None,
) -> None:
    """Assert that actual fabric row matches expected values.

    Parameters
    ----------
    actual:
        Row read from fabric.
    expected:
        Expected field values.
    ignore_fields:
        Fields to skip in comparison (e.g., auto-generated timestamps).
    """
    ignore = ignore_fields or set()
    for key, expected_value in expected.items():
        if key in ignore:
            continue
        assert key in actual, f"Missing field '{key}' in actual row"
        assert (
            actual[key] == expected_value
        ), f"Field '{key}' mismatch: expected {expected_value!r}, got {actual[key]!r}"


def assert_no_future_leak(
    rows: list[dict[str, Any]],
    cutoff_date: str,
    date_field: str = "period_end",
) -> None:
    """Assert that no rows contain dates after the cutoff.

    This is the PIT discipline enforcement: no future data should
    be visible at any point in time.

    Parameters
    ----------
    rows:
        Fabric rows to check.
    cutoff_date:
        The latest allowed date (ISO format string).
    date_field:
        The field containing the date to check.

    Raises
    ------
    AssertionError
        If any row has a date after the cutoff.
    """
    for row in rows:
        date_val = row.get(date_field, "")
        assert date_val <= cutoff_date, (
            f"Future data leak: {date_field}={date_val} > cutoff={cutoff_date} "
            f"in row {row.get('id', 'unknown')}"
        )
