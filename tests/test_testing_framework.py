"""Tests for the Midas testing infrastructure (midas.testing).

Covers:
- assertions.assert_pit_tuple: PIT tuple validation
- assertions.assert_fabric_row_matches: row field matching
- assertions.assert_no_future_leak: future date detection
- fixtures.FabricTestFixture: DataFlow instance lifecycle, table setup, helpers
- fixtures.create_test_fabric: convenience factory function

Tier 1 for assertion functions (pure logic, no I/O).
Tier 2 for fixture tests (real SQLite DataFlow instance).

Ref: specs/13 (Testing Infrastructure), rules/testing.md (3-tier strategy)
"""

import os
import tempfile

import pytest

from midas.testing.assertions import (
    assert_fabric_row_matches,
    assert_no_future_leak,
    assert_pit_tuple,
)
from midas.testing.fixtures import FabricTestFixture, create_test_fabric


# ===========================================================================
# assert_pit_tuple
# ===========================================================================


class TestAssertPitTuple:
    """assert_pit_tuple validates that a fabric row carries a valid PIT tuple."""

    def test_valid_complete_tuple_passes(self):
        """Row with all four PIT fields passes without error."""
        row = {
            "period_end": "2026-03-31",
            "filed_at": "2026-04-15",
            "restated_at": "",
            "source_vintage": "eodhd:2026-04-15T10:00:00Z",
        }
        assert_pit_tuple(row)

    def test_valid_with_restated_at(self):
        """Row where restated_at is populated passes."""
        row = {
            "period_end": "2026-03-31",
            "filed_at": "2026-04-15",
            "restated_at": "2026-04-16",
            "source_vintage": "eodhd:2026-04-16T08:00:00Z",
        }
        assert_pit_tuple(row)

    def test_restated_at_empty_string_allowed(self):
        """restated_at may be an empty string (never restated)."""
        row = {
            "period_end": "2026-03-31",
            "filed_at": "2026-04-15",
            "restated_at": "",
            "source_vintage": "eodhd:2026-04-15T10:00:00Z",
        }
        assert_pit_tuple(row)

    def test_require_filed_at_false_skips_filed_at_check(self):
        """When require_filed_at=False, missing filed_at does not fail."""
        row = {
            "period_end": "2026-03-31",
            "restated_at": "",
            "source_vintage": "eodhd:2026-04-15",
        }
        assert_pit_tuple(row, require_filed_at=False)

    def test_require_filed_at_false_empty_filed_at_passes(self):
        """When require_filed_at=False, empty filed_at does not fail."""
        row = {
            "period_end": "2026-03-31",
            "filed_at": "",
            "restated_at": "",
            "source_vintage": "eodhd:2026-04-15",
        }
        assert_pit_tuple(row, require_filed_at=False)

    def test_missing_period_end_raises(self):
        """Missing period_end raises AssertionError."""
        row = {
            "filed_at": "2026-04-15",
            "restated_at": "",
            "source_vintage": "eodhd:2026-04-15",
        }
        with pytest.raises(AssertionError, match="period_end"):
            assert_pit_tuple(row)

    def test_missing_filed_at_raises(self):
        """Missing filed_at raises AssertionError when required (default)."""
        row = {
            "period_end": "2026-03-31",
            "restated_at": "",
            "source_vintage": "eodhd:2026-04-15",
        }
        with pytest.raises(AssertionError, match="filed_at"):
            assert_pit_tuple(row)

    def test_empty_filed_at_raises_when_required(self):
        """Empty filed_at raises AssertionError when require_filed_at=True."""
        row = {
            "period_end": "2026-03-31",
            "filed_at": "",
            "restated_at": "",
            "source_vintage": "eodhd:2026-04-15",
        }
        with pytest.raises(AssertionError, match="filed_at must be non-empty"):
            assert_pit_tuple(row, require_filed_at=True)

    def test_missing_restated_at_raises(self):
        """Missing restated_at raises AssertionError."""
        row = {
            "period_end": "2026-03-31",
            "filed_at": "2026-04-15",
            "source_vintage": "eodhd:2026-04-15",
        }
        with pytest.raises(AssertionError, match="restated_at"):
            assert_pit_tuple(row)

    def test_missing_source_vintage_raises(self):
        """Missing source_vintage raises AssertionError."""
        row = {
            "period_end": "2026-03-31",
            "filed_at": "2026-04-15",
            "restated_at": "",
        }
        with pytest.raises(AssertionError, match="source_vintage"):
            assert_pit_tuple(row)

    def test_missing_all_pit_fields_raises(self):
        """Row with no PIT fields raises on the first check (period_end)."""
        row = {"ticker": "AAPL", "close": 150.0}
        with pytest.raises(AssertionError, match="period_end"):
            assert_pit_tuple(row)

    def test_error_message_includes_available_keys(self):
        """Error message shows which keys are present for debugging."""
        row = {"ticker": "AAPL", "close": 150.0}
        with pytest.raises(AssertionError, match="ticker"):
            assert_pit_tuple(row)

    def test_row_with_extra_fields_passes(self):
        """Extra fields beyond the PIT tuple are ignored."""
        row = {
            "id": 1,
            "ticker": "AAPL",
            "period_end": "2026-03-31",
            "filed_at": "2026-04-15",
            "restated_at": "",
            "source_vintage": "eodhd:2026-04-15",
            "close": 150.0,
            "volume": 1000000,
        }
        assert_pit_tuple(row)


# ===========================================================================
# assert_fabric_row_matches
# ===========================================================================


class TestAssertFabricRowMatches:
    """assert_fabric_row_matches verifies actual row fields against expected."""

    def test_exact_match_passes(self):
        """Identical dicts pass without error."""
        actual = {"ticker": "AAPL", "close": 150.0, "volume": 1000}
        expected = {"ticker": "AAPL", "close": 150.0, "volume": 1000}
        assert_fabric_row_matches(actual, expected)

    def test_partial_match_passes(self):
        """Only expected fields are checked; extra actual fields are ignored."""
        actual = {"ticker": "AAPL", "close": 150.0, "volume": 1000, "id": 1}
        expected = {"ticker": "AAPL", "close": 150.0}
        assert_fabric_row_matches(actual, expected)

    def test_missing_field_in_actual_raises(self):
        """Expected key absent from actual raises AssertionError."""
        actual = {"ticker": "AAPL", "close": 150.0}
        expected = {"ticker": "AAPL", "close": 150.0, "volume": 1000}
        with pytest.raises(AssertionError, match="Missing field 'volume'"):
            assert_fabric_row_matches(actual, expected)

    def test_value_mismatch_raises(self):
        """Mismatched value for a key raises AssertionError."""
        actual = {"ticker": "AAPL", "close": 151.0}
        expected = {"ticker": "AAPL", "close": 150.0}
        with pytest.raises(AssertionError, match="close"):
            assert_fabric_row_matches(actual, expected)

    def test_mismatch_error_shows_expected_and_actual(self):
        """Error message includes both the expected and actual values."""
        actual = {"status": "pending"}
        expected = {"status": "filled"}
        with pytest.raises(AssertionError, match="filled") as exc_info:
            assert_fabric_row_matches(actual, expected)
        assert "pending" in str(exc_info.value)

    def test_ignore_fields_skips_comparison(self):
        """Fields listed in ignore_fields are not compared."""
        actual = {"ticker": "AAPL", "updated_at": "2026-04-16T12:00:00"}
        expected = {"ticker": "AAPL", "updated_at": "2026-04-15T10:00:00"}
        assert_fabric_row_matches(actual, expected, ignore_fields={"updated_at"})

    def test_ignore_fields_empty_set_no_effect(self):
        """Empty ignore set does not skip any fields."""
        actual = {"ticker": "AAPL"}
        expected = {"ticker": "AAPL"}
        assert_fabric_row_matches(actual, expected, ignore_fields=set())

    def test_ignore_multiple_fields(self):
        """Multiple ignore fields are all skipped."""
        actual = {"ticker": "AAPL", "ts1": "a", "ts2": "b"}
        expected = {"ticker": "AAPL", "ts1": "different", "ts2": "also_different"}
        assert_fabric_row_matches(actual, expected, ignore_fields={"ts1", "ts2"})

    def test_empty_expected_passes(self):
        """Empty expected dict always passes (nothing to check)."""
        actual = {"ticker": "AAPL", "close": 150.0}
        assert_fabric_row_matches(actual, {})

    def test_string_type_mismatch(self):
        """String '150.0' does not match float 150.0."""
        actual = {"close": "150.0"}
        expected = {"close": 150.0}
        with pytest.raises(AssertionError, match="close"):
            assert_fabric_row_matches(actual, expected)

    def test_none_vs_empty_string(self):
        """None does not match empty string."""
        actual = {"field": None}
        expected = {"field": ""}
        with pytest.raises(AssertionError, match="field"):
            assert_fabric_row_matches(actual, expected)

    def test_nested_value_comparison(self):
        """Nested structures are compared by equality."""
        actual = {"data": {"nested": True, "value": 42}}
        expected = {"data": {"nested": True, "value": 42}}
        assert_fabric_row_matches(actual, expected)

    def test_nested_value_mismatch(self):
        """Mismatched nested structures raise."""
        actual = {"data": {"nested": True}}
        expected = {"data": {"nested": False}}
        with pytest.raises(AssertionError, match="data"):
            assert_fabric_row_matches(actual, expected)

    def test_list_value_comparison(self):
        """List values are compared by equality."""
        actual = {"tags": ["a", "b", "c"]}
        expected = {"tags": ["a", "b", "c"]}
        assert_fabric_row_matches(actual, expected)

    def test_list_value_mismatch(self):
        """Mismatched list values raise."""
        actual = {"tags": ["a", "b"]}
        expected = {"tags": ["a", "b", "c"]}
        with pytest.raises(AssertionError, match="tags"):
            assert_fabric_row_matches(actual, expected)

    def test_ignore_fields_none_treated_as_empty(self):
        """ignore_fields=None behaves like an empty set (default)."""
        actual = {"ticker": "AAPL"}
        expected = {"ticker": "MSFT"}
        with pytest.raises(AssertionError, match="ticker"):
            assert_fabric_row_matches(actual, expected, ignore_fields=None)


# ===========================================================================
# assert_no_future_leak
# ===========================================================================


class TestAssertNoFutureLeak:
    """assert_no_future_leak verifies no rows exceed the cutoff date."""

    def test_all_rows_before_cutoff_passes(self):
        """Rows with dates at or before cutoff pass."""
        rows = [
            {"id": 1, "period_end": "2026-01-31"},
            {"id": 2, "period_end": "2026-02-28"},
            {"id": 3, "period_end": "2026-03-31"},
        ]
        assert_no_future_leak(rows, cutoff_date="2026-03-31")

    def test_row_at_exactly_cutoff_passes(self):
        """Row with date exactly equal to cutoff passes (inclusive)."""
        rows = [{"id": 1, "period_end": "2026-03-31"}]
        assert_no_future_leak(rows, cutoff_date="2026-03-31")

    def test_row_after_cutoff_raises(self):
        """Row with date after cutoff raises AssertionError."""
        rows = [{"id": 1, "period_end": "2026-04-30"}]
        with pytest.raises(AssertionError, match="Future data leak"):
            assert_no_future_leak(rows, cutoff_date="2026-03-31")

    def test_leak_error_shows_row_id(self):
        """Error message identifies the leaking row by id."""
        rows = [{"id": 42, "period_end": "2026-12-31"}]
        with pytest.raises(AssertionError, match="42"):
            assert_no_future_leak(rows, cutoff_date="2026-03-31")

    def test_leak_error_shows_date_and_cutoff(self):
        """Error message includes both the leak date and cutoff."""
        rows = [{"id": 1, "period_end": "2026-12-31"}]
        with pytest.raises(AssertionError, match="2026-12-31") as exc_info:
            assert_no_future_leak(rows, cutoff_date="2026-03-31")
        assert "2026-03-31" in str(exc_info.value)

    def test_empty_rows_passes(self):
        """Empty list of rows passes trivially."""
        assert_no_future_leak([], cutoff_date="2026-03-31")

    def test_mixed_rows_one_leak_raises(self):
        """One future row among valid rows raises."""
        rows = [
            {"id": 1, "period_end": "2026-01-31"},
            {"id": 2, "period_end": "2026-06-30"},
            {"id": 3, "period_end": "2026-02-28"},
        ]
        with pytest.raises(AssertionError, match="Future data leak"):
            assert_no_future_leak(rows, cutoff_date="2026-03-31")

    def test_custom_date_field(self):
        """date_field parameter selects which field to check."""
        rows = [
            {"id": 1, "filed_at": "2026-04-15", "period_end": "2026-03-31"},
        ]
        # Check against filed_at, not period_end
        assert_no_future_leak(rows, cutoff_date="2026-04-15", date_field="filed_at")

    def test_custom_date_field_future_raises(self):
        """Custom date_field detects future values in that field."""
        rows = [
            {"id": 1, "filed_at": "2026-12-31", "period_end": "2026-03-31"},
        ]
        with pytest.raises(AssertionError, match="Future data leak"):
            assert_no_future_leak(rows, cutoff_date="2026-04-15", date_field="filed_at")

    def test_missing_date_field_treated_as_empty(self):
        """Row missing the date_field uses empty string, which is <= any date."""
        rows = [{"id": 1, "ticker": "AAPL"}]
        assert_no_future_leak(rows, cutoff_date="2026-03-31", date_field="period_end")

    def test_unknown_row_shows_id_unknown(self):
        """Row without 'id' field shows 'unknown' in error message."""
        rows = [{"period_end": "2026-12-31"}]
        with pytest.raises(AssertionError, match="unknown"):
            assert_no_future_leak(rows, cutoff_date="2026-03-31")

    def test_lexicographic_comparison(self):
        """ISO date strings are compared lexicographically (works for ISO format)."""
        rows = [
            {"id": 1, "period_end": "2026-01-01"},
            {"id": 2, "period_end": "2026-12-31"},
        ]
        with pytest.raises(AssertionError):
            assert_no_future_leak(rows, cutoff_date="2026-06-30")

    def test_all_rows_after_cutoff_raises_on_first(self):
        """Multiple future rows raise on the first one encountered."""
        rows = [
            {"id": 1, "period_end": "2026-07-31"},
            {"id": 2, "period_end": "2026-08-31"},
        ]
        with pytest.raises(AssertionError, match="1"):
            assert_no_future_leak(rows, cutoff_date="2026-03-31")


# ===========================================================================
# FabricTestFixture
# ===========================================================================


class TestFabricTestFixture:
    """FabricTestFixture manages DataFlow lifecycle for tests."""

    @pytest.mark.asyncio
    async def test_setup_creates_database(self):
        """setup() returns a started DataFlow instance."""
        fixture = FabricTestFixture()
        db = await fixture.setup()

        assert db is not None
        assert fixture.db is db

        await fixture.teardown()

    @pytest.mark.asyncio
    async def test_setup_creates_temp_file(self):
        """setup() creates a temp SQLite file for the database."""
        fixture = FabricTestFixture()
        await fixture.setup()

        assert fixture._db_path != ""
        assert os.path.dirname(fixture._db_path) == fixture._tmpdir

        await fixture.teardown()

    @pytest.mark.asyncio
    async def test_teardown_cleans_database(self):
        """teardown() sets db to None after cleanup."""
        fixture = FabricTestFixture()
        await fixture.setup()

        assert fixture.db is not None

        await fixture.teardown()

        assert fixture.db is None

    @pytest.mark.asyncio
    async def test_teardown_removes_sqlite_files(self):
        """teardown() removes the SQLite database file and its WAL/SHM."""
        fixture = FabricTestFixture()
        await fixture.setup()
        db_path = fixture._db_path

        await fixture.teardown()

        assert not os.path.exists(db_path)
        assert not os.path.exists(db_path + "-wal")
        assert not os.path.exists(db_path + "-shm")

    @pytest.mark.asyncio
    async def test_teardown_removes_temp_directory(self):
        """teardown() removes the temporary directory."""
        fixture = FabricTestFixture()
        await fixture.setup()
        tmpdir = fixture._tmpdir

        await fixture.teardown()

        assert not os.path.exists(tmpdir)

    @pytest.mark.asyncio
    async def test_teardown_idempotent(self):
        """Calling teardown() twice does not raise."""
        fixture = FabricTestFixture()
        await fixture.setup()
        await fixture.teardown()
        await fixture.teardown()  # second call should not raise

    @pytest.mark.asyncio
    async def test_teardown_without_setup(self):
        """Calling teardown() before setup() does not raise."""
        fixture = FabricTestFixture()
        await fixture.teardown()  # should not raise

    @pytest.mark.asyncio
    async def test_create_row_returns_created_row(self):
        """create_row() inserts data and returns the matching row."""
        fixture = FabricTestFixture()
        db = await fixture.setup()

        try:
            data = {
                "ticker": "AAPL",
                "period_end": "2026-03-31",
                "close": 150.0,
                "volume": 1000000,
                "filed_at": "2026-04-15",
                "restated_at": "",
                "source_vintage": "test",
            }
            result = await fixture.create_row("prices", data)

            assert result["ticker"] == "AAPL"
            assert result["close"] == 150.0
            assert result["volume"] == 1000000
        finally:
            await fixture.teardown()

    @pytest.mark.asyncio
    async def test_create_row_without_setup_raises(self):
        """create_row() raises if setup() was not called."""
        fixture = FabricTestFixture()

        with pytest.raises(AssertionError, match="setup"):
            await fixture.create_row("prices", {"ticker": "AAPL"})

    @pytest.mark.asyncio
    async def test_create_rows_returns_all(self):
        """create_rows() inserts multiple rows and returns them all."""
        fixture = FabricTestFixture()
        db = await fixture.setup()

        try:
            rows_data = [
                {
                    "ticker": "AAPL",
                    "period_end": "2026-01-31",
                    "close": 148.0,
                    "volume": 500000,
                    "filed_at": "2026-02-15",
                    "restated_at": "",
                    "source_vintage": "test",
                },
                {
                    "ticker": "MSFT",
                    "period_end": "2026-01-31",
                    "close": 380.0,
                    "volume": 300000,
                    "filed_at": "2026-02-15",
                    "restated_at": "",
                    "source_vintage": "test",
                },
            ]
            results = await fixture.create_rows("prices", rows_data)

            assert len(results) == 2
            tickers = {r["ticker"] for r in results}
            assert tickers == {"AAPL", "MSFT"}
        finally:
            await fixture.teardown()

    @pytest.mark.asyncio
    async def test_create_rows_empty_list_returns_empty(self):
        """create_rows() with an empty list returns empty list."""
        fixture = FabricTestFixture()
        await fixture.setup()

        try:
            results = await fixture.create_rows("prices", [])
            assert results == []
        finally:
            await fixture.teardown()

    @pytest.mark.asyncio
    async def test_fabric_tables_registered(self):
        """All fabric tables are accessible after setup."""
        from midas.fabric.engine import FABRIC_TABLES

        fixture = FabricTestFixture()
        db = await fixture.setup()

        try:
            # Verify a core set of tables work by inserting and reading
            core_tables_to_test = [
                (
                    "prices",
                    {
                        "ticker": "TEST",
                        "period_end": "2026-01-01",
                        "filed_at": "2026-01-01",
                        "restated_at": "",
                        "source_vintage": "",
                    },
                ),
                (
                    "fundamentals",
                    {
                        "ticker": "TEST",
                        "period_end": "2026-01-01",
                        "filed_at": "2026-01-01",
                        "restated_at": "",
                        "source_vintage": "",
                    },
                ),
                (
                    "macro",
                    {
                        "series_name": "GDP",
                        "period_end": "2026-01-01",
                        "filed_at": "2026-01-01",
                        "restated_at": "",
                        "source_vintage": "",
                    },
                ),
            ]
            for table_name, data in core_tables_to_test:
                await db.express.create(table_name, data)
                rows = await db.express.list(table_name, filter={})
                assert len(rows) >= 1, f"Table {table_name} should have at least 1 row"
        finally:
            await fixture.teardown()


# ===========================================================================
# create_test_fabric
# ===========================================================================


class TestCreateTestFabric:
    """create_test_fabric() convenience factory function."""

    @pytest.mark.asyncio
    async def test_returns_db_and_fixture(self):
        """create_test_fabric returns a (DataFlow, FabricTestFixture) tuple."""
        db, fixture = await create_test_fabric()

        assert db is not None
        assert isinstance(fixture, FabricTestFixture)

        await fixture.teardown()

    @pytest.mark.asyncio
    async def test_returned_db_is_usable(self):
        """The returned DataFlow instance can create and list rows."""
        db, fixture = await create_test_fabric()

        try:
            data = {
                "ticker": "SPY",
                "period_end": "2026-03-31",
                "close": 450.0,
                "volume": 5000000,
                "filed_at": "2026-04-15",
                "restated_at": "",
                "source_vintage": "test",
            }
            await db.express.create("prices", data)
            rows = await db.express.list("prices", filter={})
            assert len(rows) == 1
            assert rows[0]["ticker"] == "SPY"
        finally:
            await fixture.teardown()

    @pytest.mark.asyncio
    async def test_fixture_teardown_cleans_up(self):
        """The returned fixture cleans up resources on teardown."""
        db, fixture = await create_test_fabric()
        db_path = fixture._db_path

        await fixture.teardown()

        assert fixture.db is None
        assert not os.path.exists(db_path)


# ===========================================================================
# Integration: assertions against fixture data
# ===========================================================================


class TestAssertionsWithFixtureData:
    """Use assertions against real fixture data to verify end-to-end."""

    @pytest.mark.asyncio
    async def test_pit_tuple_on_real_fabric_row(self):
        """assert_pit_tuple works on a row created via FabricTestFixture."""
        fixture = FabricTestFixture()
        await fixture.setup()

        try:
            data = {
                "ticker": "AAPL",
                "period_end": "2026-03-31",
                "close": 150.0,
                "volume": 1000000,
                "filed_at": "2026-04-15",
                "restated_at": "",
                "source_vintage": "test:v1",
            }
            row = await fixture.create_row("prices", data)
            assert_pit_tuple(row)
        finally:
            await fixture.teardown()

    @pytest.mark.asyncio
    async def test_fabric_row_matches_on_real_data(self):
        """assert_fabric_row_matches works on rows from the fixture."""
        fixture = FabricTestFixture()
        await fixture.setup()

        try:
            data = {
                "ticker": "MSFT",
                "period_end": "2026-03-31",
                "close": 380.0,
                "volume": 2000000,
                "filed_at": "2026-04-15",
                "restated_at": "",
                "source_vintage": "test:v1",
            }
            row = await fixture.create_row("prices", data)
            assert_fabric_row_matches(
                row,
                {"ticker": "MSFT", "close": 380.0},
                ignore_fields={"id", "created_at", "updated_at"},
            )
        finally:
            await fixture.teardown()

    @pytest.mark.asyncio
    async def test_no_future_leak_on_real_data(self):
        """assert_no_future_leak passes for rows within cutoff."""
        fixture = FabricTestFixture()
        await fixture.setup()

        try:
            rows_data = [
                {
                    "ticker": "AAPL",
                    "period_end": "2026-01-31",
                    "close": 148.0,
                    "volume": 500000,
                    "filed_at": "2026-02-15",
                    "restated_at": "",
                    "source_vintage": "test",
                },
                {
                    "ticker": "AAPL",
                    "period_end": "2026-02-28",
                    "close": 149.0,
                    "volume": 600000,
                    "filed_at": "2026-03-15",
                    "restated_at": "",
                    "source_vintage": "test",
                },
            ]
            rows = await fixture.create_rows("prices", rows_data)
            assert_no_future_leak(rows, cutoff_date="2026-03-31")
        finally:
            await fixture.teardown()

    @pytest.mark.asyncio
    async def test_future_leak_detected_on_real_data(self):
        """assert_no_future_leak raises when a future-dated row is present."""
        fixture = FabricTestFixture()
        await fixture.setup()

        try:
            rows_data = [
                {
                    "ticker": "AAPL",
                    "period_end": "2026-01-31",
                    "close": 148.0,
                    "volume": 500000,
                    "filed_at": "2026-02-15",
                    "restated_at": "",
                    "source_vintage": "test",
                },
                {
                    "ticker": "AAPL",
                    "period_end": "2026-12-31",
                    "close": 200.0,
                    "volume": 700000,
                    "filed_at": "2027-01-15",
                    "restated_at": "",
                    "source_vintage": "test",
                },
            ]
            rows = await fixture.create_rows("prices", rows_data)

            with pytest.raises(AssertionError, match="Future data leak"):
                assert_no_future_leak(rows, cutoff_date="2026-06-30")
        finally:
            await fixture.teardown()
