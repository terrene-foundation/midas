"""Tests for Gap 2: Multi-level demotion in the autonomy ladder.

Verifies demote_to, demote_by_trigger, and the DEMOTE_TARGET mapping
against specs/08-autonomy-and-trust.md S4.
"""

import os
import tempfile

import pytest

from midas.autonomy.ladder import (
    AutonomyLadder,
    AutonomyLevel,
    DEMOTE_TARGET,
)
from midas.fabric.engine import create_fabric, reset_fabric


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for ladder tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_ladder_demote.db")
    db_url = f"sqlite:///{db_path}"
    database = create_fabric(database_url=db_url, auto_migrate=True)
    yield database
    try:
        database.close()
    except Exception:
        pass
    reset_fabric()
    for suffix in ("-wal", "-shm"):
        try:
            os.unlink(db_path + suffix)
        except OSError:
            pass
    try:
        os.unlink(db_path)
    except OSError:
        pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass


@pytest.fixture
async def started_db(db):
    """Start the database for async tests."""
    await db.start()
    yield db
    try:
        await db.close_async()
    except Exception:
        pass


async def _promote_to(ladder: AutonomyLadder, target: AutonomyLevel) -> None:
    """Helper: promote the ladder from L0 to the target level.

    Works around the first-seven-days constraint by directly clearing
    the flag after the L0->L1 transition, since ladder internals need
    the state to allow higher promotions.
    """
    from datetime import datetime, timedelta, timezone

    for level in range(int(target)):
        result = await ladder.request_promotion(
            target_level=AutonomyLevel(level + 1),
            evidence={"paper_trading_complete": True, "report_reviewed": True},
            user_approved=True,
        )
        assert result["success"] is True, (
            f"Failed to promote to L{level + 1}: {result['reason']}"
        )
        # After L1 promotion, clear the first-seven-days constraint by
        # setting the live_start_date far enough in the past
        if level == 0:
            ladder._state.first_seven_days_active = False
            # Set live start date far enough back to pass the 7-day check
            ladder._state.live_start_date = (
                datetime.now(timezone.utc) - timedelta(days=30)
            ).isoformat()


# ---------------------------------------------------------------------------
# Gap 2: demote_to
# ---------------------------------------------------------------------------


class TestDemoteTo:
    """Tests for the demote_to method (multi-level demotion)."""

    @pytest.mark.asyncio
    async def test_demote_to_drops_multiple_levels(self, started_db):
        """demote_to from L4 to L1 skips L3 and L2."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L4)
        result = await ladder.demote_to(
            target_level=AutonomyLevel.L1,
            reason="drawdown breach",
            trigger="drawdown_breach",
        )
        assert result["success"] is True
        assert result["new_level"] == AutonomyLevel.L1

    @pytest.mark.asyncio
    async def test_demote_to_from_l3_to_l0(self, started_db):
        """demote_to can drop from L3 directly to L0."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L3)
        result = await ladder.demote_to(
            target_level=AutonomyLevel.L0,
            reason="kill switch",
            trigger="kill_switch",
        )
        assert result["success"] is True
        assert result["new_level"] == AutonomyLevel.L0

    @pytest.mark.asyncio
    async def test_demote_to_at_l0_is_noop(self, started_db):
        """demote_to at L0 stays at L0."""
        ladder = AutonomyLadder(started_db)
        result = await ladder.demote_to(
            target_level=AutonomyLevel.L0,
            reason="already at floor",
            trigger="kill_switch",
        )
        assert result["success"] is True
        assert result["new_level"] == AutonomyLevel.L0

    @pytest.mark.asyncio
    async def test_demote_to_rejects_higher_target(self, started_db):
        """demote_to rejects a target that is not lower than current."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L2)
        result = await ladder.demote_to(
            target_level=AutonomyLevel.L3,
            reason="invalid",
            trigger="test",
        )
        assert result["success"] is False
        assert result["new_level"] == AutonomyLevel.L2

    @pytest.mark.asyncio
    async def test_demote_to_rejects_same_level(self, started_db):
        """demote_to rejects a target equal to current level."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L2)
        result = await ladder.demote_to(
            target_level=AutonomyLevel.L2,
            reason="no change",
            trigger="test",
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_demote_to_creates_audit_record(self, started_db):
        """demote_to writes an audit record with multi_level flag."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L4)
        await ladder.demote_to(
            target_level=AutonomyLevel.L1,
            reason="test",
            trigger="drawdown_breach",
        )
        rows = await started_db.express.list("audit_log")
        demotion_rows = [r for r in rows if r.get("action") == "demotion"]
        assert len(demotion_rows) >= 1
        import json
        details = json.loads(demotion_rows[-1].get("details", "{}"))
        assert details.get("multi_level") is True
        assert details.get("from_level") == 4
        assert details.get("to_level") == 1

    @pytest.mark.asyncio
    async def test_demote_to_increments_demotion_count(self, started_db):
        """demote_to increments the demotion counter."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L4)
        await ladder.demote_to(
            target_level=AutonomyLevel.L1,
            reason="test",
            trigger="test",
        )
        state = await ladder.get_current_state()
        assert state.demotion_count == 1


# ---------------------------------------------------------------------------
# Gap 2: demote_by_trigger
# ---------------------------------------------------------------------------


class TestDemoteByTrigger:
    """Tests for trigger-specific demotion via demote_by_trigger."""

    @pytest.mark.asyncio
    async def test_drawdown_breach_l3_to_l1(self, started_db):
        """Drawdown breach demotes L3 to L1 per spec S4."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L3)
        result = await ladder.demote_by_trigger(
            trigger="drawdown_breach",
            reason="Drawdown exceeded envelope ceiling",
        )
        assert result["success"] is True
        assert result["new_level"] == AutonomyLevel.L1

    @pytest.mark.asyncio
    async def test_drawdown_breach_l4_to_l1(self, started_db):
        """Drawdown breach demotes L4 to L1 per spec S4."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L4)
        result = await ladder.demote_by_trigger(
            trigger="drawdown_breach",
            reason="Drawdown exceeded envelope ceiling",
        )
        assert result["success"] is True
        assert result["new_level"] == AutonomyLevel.L1

    @pytest.mark.asyncio
    async def test_crisis_band_l3_to_l2(self, started_db):
        """Crisis band demotes L3 to L2 per spec S4."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L3)
        result = await ladder.demote_by_trigger(
            trigger="crisis_band",
            reason="Crisis band entered",
        )
        assert result["success"] is True
        assert result["new_level"] == AutonomyLevel.L2

    @pytest.mark.asyncio
    async def test_crisis_band_l4_to_l2(self, started_db):
        """Crisis band demotes L4 to L2 per spec S4."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L4)
        result = await ladder.demote_by_trigger(
            trigger="crisis_band",
            reason="Crisis band entered",
        )
        assert result["success"] is True
        assert result["new_level"] == AutonomyLevel.L2

    @pytest.mark.asyncio
    async def test_kill_switch_any_to_l0(self, started_db):
        """Kill switch demotes any level to L0 per spec S4."""
        for start_level in [AutonomyLevel.L1, AutonomyLevel.L2, AutonomyLevel.L3, AutonomyLevel.L4]:
            ladder = AutonomyLadder(started_db)
            await _promote_to(ladder, start_level)
            result = await ladder.demote_by_trigger(
                trigger="kill_switch",
                reason="Kill switch activated",
            )
            assert result["new_level"] == AutonomyLevel.L0, (
                f"Kill switch should demote L{int(start_level)} to L0"
            )

    @pytest.mark.asyncio
    async def test_model_failure_l3_to_l2(self, started_db):
        """Model failure demotes L3 to L2 per spec S4."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L3)
        result = await ladder.demote_by_trigger(
            trigger="model_failure",
            reason="Champion model demoted",
        )
        assert result["new_level"] == AutonomyLevel.L2

    @pytest.mark.asyncio
    async def test_model_failure_l4_to_l2(self, started_db):
        """Model failure demotes L4 to L2 per spec S4."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L4)
        result = await ladder.demote_by_trigger(
            trigger="model_failure",
            reason="Champion model demoted",
        )
        assert result["new_level"] == AutonomyLevel.L2

    @pytest.mark.asyncio
    async def test_unknown_trigger_falls_back_to_single_level(self, started_db):
        """Unknown trigger falls back to single-level demote."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L3)
        result = await ladder.demote_by_trigger(
            trigger="unknown_trigger",
            reason="Unknown cause",
        )
        assert result["success"] is True
        # Falls back to single-level: L3 -> L2
        assert result["new_level"] == AutonomyLevel.L2

    @pytest.mark.asyncio
    async def test_no_mapping_at_l1_is_noop(self, started_db):
        """Trigger with no mapping for current level is a no-op."""
        ladder = AutonomyLadder(started_db)
        await _promote_to(ladder, AutonomyLevel.L1)
        result = await ladder.demote_by_trigger(
            trigger="drawdown_breach",
            reason="Drawdown at L1",
        )
        # drawdown_breach only maps L3/L4, so L1 should stay
        assert result["success"] is True
        assert result["new_level"] == AutonomyLevel.L1


# ---------------------------------------------------------------------------
# Gap 2: DEMOTE_TARGET mapping coverage
# ---------------------------------------------------------------------------


class TestDemoteTargetMapping:
    """Tests for the DEMOTE_TARGET trigger mapping table."""

    def test_all_spec_triggers_present(self):
        """DEMOTE_TARGET contains mappings for all spec-defined triggers."""
        required_triggers = [
            "drawdown_breach",
            "crisis_band",
            "kill_switch",
            "model_failure",
            "ood_detected",
            "override_rate",
        ]
        for trigger in required_triggers:
            assert trigger in DEMOTE_TARGET, f"Missing trigger mapping: {trigger}"

    def test_kill_switch_maps_all_levels_to_l0(self):
        """Kill switch mapping sends every level to L0."""
        for level in range(5):
            assert DEMOTE_TARGET["kill_switch"][level] == 0

    def test_drawdown_breach_maps_l3_l4_to_l1(self):
        """Drawdown breach sends L3 and L4 to L1."""
        assert DEMOTE_TARGET["drawdown_breach"][3] == 1
        assert DEMOTE_TARGET["drawdown_breach"][4] == 1

    def test_crisis_band_maps_l3_l4_to_l2(self):
        """Crisis band sends L3 and L4 to L2."""
        assert DEMOTE_TARGET["crisis_band"][3] == 2
        assert DEMOTE_TARGET["crisis_band"][4] == 2

    def test_model_failure_maps_l3_l4_to_l2(self):
        """Model failure sends L3 and L4 to L2."""
        assert DEMOTE_TARGET["model_failure"][3] == 2
        assert DEMOTE_TARGET["model_failure"][4] == 2

    def test_override_rate_maps_l3_to_l2_and_l2_to_l1(self):
        """Override rate sends L3 to L2 and L2 to L1."""
        assert DEMOTE_TARGET["override_rate"][3] == 2
        assert DEMOTE_TARGET["override_rate"][2] == 1
