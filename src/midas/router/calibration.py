"""
Inner loop: continuous calibration tracking for per-head reliability.

Records predictions and actual outcomes, computes calibration curves,
and returns local reliability scores for each head in a z_t neighborhood.

Ref: specs/06-meta-router.md
"""

import json
import math

import structlog
from dataflow import DataFlow

logger = structlog.get_logger(__name__)


class CalibrationService:
    """Per-head calibration tracking backed by the audit_log fabric table."""

    def __init__(self, db: DataFlow) -> None:
        self._db = db

    async def record_prediction(
        self,
        head_name: str,
        z_t_hash: str,
        horizon: int,
        prediction: dict,
        actual_outcome: dict | None = None,
    ) -> None:
        """Record a prediction and optionally its outcome.

        Writes a row to the audit_log table with action=calibration_record
        so that calibration data coexists with other audit entries and
        remains queryable by head name, z_t neighborhood, and horizon.
        """
        details = json.dumps(
            {
                "head_name": head_name,
                "z_t_hash": z_t_hash,
                "horizon": horizon,
                "prediction": prediction,
                "actual_outcome": actual_outcome,
            }
        )

        row = {
            "rule_name": "calibration",
            "action": "calibration_record",
            "details": details,
            "severity": "info",
            "agent": head_name,
            "z_t_snapshot": z_t_hash,
        }

        await self._db.express.create("audit_log", row)
        logger.debug(
            "calibration.recorded",
            head=head_name,
            z_t_hash=z_t_hash,
            horizon=horizon,
            has_outcome=actual_outcome is not None,
        )

    async def compute_calibration_curve(
        self,
        head_name: str,
        horizon: int,
        n_bins: int = 10,
    ) -> list[dict]:
        """Compute calibration curve (predicted probability vs actual frequency).

        Reads all calibration records for the given head and horizon, bins
        them by predicted probability, and returns per-bin statistics.
        """
        rows = await self._db.express.list("audit_log")
        calibration_rows = [
            r
            for r in rows
            if r.get("action") == "calibration_record" and r.get("agent") == head_name
        ]

        # Parse details and filter by horizon
        records: list[dict] = []
        for row in calibration_rows:
            try:
                details = json.loads(row.get("details", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue
            if details.get("horizon") != horizon:
                continue
            records.append(details)

        if not records:
            return [
                {"predicted_mean": 0.0, "actual_frequency": 0.0, "count": 0} for _ in range(n_bins)
            ]

        # Bin by predicted probability
        bin_width = 1.0 / n_bins
        bins: list[list[dict]] = [[] for _ in range(n_bins)]

        for rec in records:
            prob = rec.get("prediction", {}).get("probability", 0.5)
            bin_idx = min(int(prob / bin_width), n_bins - 1)
            bins[bin_idx].append(rec)

        curve: list[dict] = []
        for bin_records in bins:
            count = len(bin_records)
            if count == 0:
                curve.append({"predicted_mean": 0.0, "actual_frequency": 0.0, "count": 0})
                continue

            predicted_mean = (
                sum(r.get("prediction", {}).get("probability", 0.5) for r in bin_records) / count
            )

            # Actual frequency: fraction where outcome direction matches prediction
            with_outcome = [r for r in bin_records if r.get("actual_outcome") is not None]
            if with_outcome:
                matches = sum(
                    1
                    for r in with_outcome
                    if r["actual_outcome"].get("direction") == r["prediction"].get("direction")
                )
                actual_frequency = matches / len(with_outcome)
            else:
                actual_frequency = 0.0

            curve.append(
                {
                    "predicted_mean": predicted_mean,
                    "actual_frequency": actual_frequency,
                    "count": count,
                }
            )

        return curve

    async def get_reliability(
        self,
        head_name: str,
        z_t_hash: str,
        horizon: int,
    ) -> float:
        """Get local reliability score for a head in a z_t neighborhood.

        Returns a value between 0.0 and 1.0 representing the fraction of
        predictions where the actual outcome matched the predicted direction.
        """
        rows = await self._db.express.list("audit_log")
        matching = [
            r
            for r in rows
            if r.get("action") == "calibration_record"
            and r.get("agent") == head_name
            and r.get("z_t_snapshot") == z_t_hash
        ]

        # Parse and filter by horizon
        records: list[dict] = []
        for row in matching:
            try:
                details = json.loads(row.get("details", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue
            if details.get("horizon") != horizon:
                continue
            records.append(details)

        with_outcome = [r for r in records if r.get("actual_outcome") is not None]
        if not with_outcome:
            return 0.5  # No data -- return neutral reliability

        matches = sum(
            1
            for r in with_outcome
            if r["actual_outcome"].get("direction") == r["prediction"].get("direction")
        )

        return matches / len(with_outcome)
