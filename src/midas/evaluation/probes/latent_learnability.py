"""
Latent-State Learnability Probe.

Before any representation-learner training runs, this probe demonstrates that
z_t is learnable from the available data using a mutual-information test.

Ref: specs/04-latent-first-architecture.md §2.2
Ref: T-00-02
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from midas.fabric.models import FabricReader, LatentStateRecord


@dataclass
class LearnabilityProbeResult:
    """Output of the latent learnability probe."""

    probe_id: str
    z_dim: int
    mi_actual: float
    mi_null_mean: float
    mi_null_std: float
    z_statistic: float
    p_value: float
    passes: bool
    min_observations_required: int
    observation_count: int
    corpus_name: str
    run_at: datetime

    def summary(self) -> str:
        return (
            f"MI={self.mi_actual:.4f} vs null μ={self.mi_null_mean:.4f} "
            f"(σ={self.mi_null_std:.4f})  z={self.z_statistic:.3f}  "
            f"p={'<0.001' if self.p_value < 0.001 else f'{self.p_value:.3f}'}  "
            f"{'PASS' if self.passes else 'FAIL'}  "
            f"(n={self.observation_count})"
        )


@dataclass
class CorpusSpec:
    """Specification of the pre-training corpus.

    Ref: T-00-02 — concrete naming of the corpus is required.
    """

    name: str
    description: str
    source_urls: tuple[str, ...]
    license_: str  # e.g. "CC BY 4.0" for academic corpora
    instruments: int  # approximate count
    date_range: tuple[date, date]
    uses: tuple[str, ...] = ("pre_train",)  # pre_train | fine_tune


# Pre-committed corpus candidates (per T-00-02 scope)
CORPUS_CANDIDATES: tuple[CorpusSpec, ...] = (
    CorpusSpec(
        name="Chronos-2 (Amazon)",
        description=(
            "Pre-trained time-series foundation model on diverse financial and"
            " macro series.  Fine-tuned on Midas fabric universe after pre-train."
        ),
        source_urls=("https://github.com/amazon-science/chronos",),
        license_="Apache 2.0",
        instruments=50000,
        date_range=(date(2000, 1, 1), date(2024, 12, 31)),
        uses=("pre_train",),
    ),
    CorpusSpec(
        name="M6-Competition CRSP-Equivalent",
        description=(
            "Cross-asset, cross-frequency financial time-series derived from"
            " M6 competition data with Ibbotson-anchored return indices."
        ),
        source_urls=("https://www.m6competition.org/",),
        license_="Research use only",
        instruments=4000,
        date_range=(date(2012, 1, 1), date(2024, 12, 31)),
        uses=("pre_train",),
    ),
    CorpusSpec(
        name="FRED-MD + FRED-E",
        description=(
            "Federal Reserve of St Louis database of 300+ macro indicators"
            " (FRED-MD) plus 130 equity factors (FRED-E). ALFRED vintage-tracking"
            " supported natively."
        ),
        source_urls=("https://fred.stlouisfed.org/categories/128",),
        license_="Public domain",
        instruments=430,
        date_range=(date(1959, 1, 1), date(2024, 12, 31)),
        uses=("pre_train", "fine_tune"),
    ),
    CorpusSpec(
        name="Midas Fabric (proprietary blend)",
        description=(
            "Midas fabric universe daily OHLCV + fundamentals + macro + alt-data."
            "  Fine-tuning target after Chronos or equivalent pre-train."
        ),
        source_urls=(),
        license_="Proprietary",
        instruments=100,  # v1: ETF universe ~100 instruments
        date_range=(date(2010, 1, 1), date(2024, 12, 31)),
        uses=("fine_tune",),
    ),
)


class LatentLearnabilityProbe:
    """Computes mutual information between z_t and realized forward returns.

    A family passes only if MI significantly exceeds the scrambled-target null.

    Invariant (a): no representation learner family is promoted to the model
    pool without passing this probe.
    Invariant (b): the probe output is stored in the model registry.

    Ref: T-00-02
    """

    MIN_OBSERVATIONS = 252  # ~1 trading year
    ALPHA = 0.05  # two-sided test vs null
    N_PERMUTATIONS = 200  # Monte Carlo for null distribution

    DEFAULT_MARKET_PROXY = "SPY"

    def __init__(self, reader: FabricReader, *, market_proxy: str = DEFAULT_MARKET_PROXY) -> None:
        self._reader = reader
        self._market_proxy = market_proxy

    async def run(
        self,
        learner_family: str,
        z_dim: int,
        as_of: date,
        forward_horizon: int = 20,
        *,
        realized_returns_override: list[float] | None = None,
    ) -> LearnabilityProbeResult:
        """Run the learnability probe for a given learner family.

        Parameters
        ----------
        learner_family: e.g. "ssl_transformer_v1", "diffusion_v2"
        z_dim: dimensionality of the candidate z_t
        as_of: point-in-time date for reading historical z_t states
        forward_horizon: number of trading days over which returns are realised
        realized_returns_override:
            Synthetic forward returns for testing. When provided, these are
            used instead of calling the fabric. Format: one float per z_record,
            NaN for invalid entries.

        Returns
        -------
        LearnabilityProbeResult with MI comparison and pass/fail decision.
        """
        # 1. Load historical z_t states + realized forward returns
        z_records = await self._reader.read_latent_state(learner_family, as_of)
        if len(z_records) < self.MIN_OBSERVATIONS:
            return LearnabilityProbeResult(
                probe_id=str(uuid.uuid4()),
                z_dim=z_dim,
                mi_actual=np.nan,
                mi_null_mean=np.nan,
                mi_null_std=np.nan,
                z_statistic=np.nan,
                p_value=1.0,
                passes=False,
                min_observations_required=self.MIN_OBSERVATIONS,
                observation_count=len(z_records),
                corpus_name=learner_family,
                run_at=datetime.now(),
            )

        z_matrix = np.array([list(r.z_vector) for r in z_records])

        if realized_returns_override is not None:
            forward_returns = np.array(realized_returns_override)
        else:
            forward_returns = np.array(
                await asyncio.gather(
                    *(self._realised_return_for_state(r, forward_horizon) for r in z_records)
                )
            )

        valid_mask = ~np.isnan(forward_returns) & ~np.any(np.isnan(z_matrix), axis=1)
        z_matrix = z_matrix[valid_mask]
        forward_returns = forward_returns[valid_mask]

        if len(forward_returns) < self.MIN_OBSERVATIONS:
            return LearnabilityProbeResult(
                probe_id=str(uuid.uuid4()),
                z_dim=z_dim,
                mi_actual=np.nan,
                mi_null_mean=np.nan,
                mi_null_std=np.nan,
                z_statistic=np.nan,
                p_value=1.0,
                passes=False,
                min_observations_required=self.MIN_OBSERVATIONS,
                observation_count=len(forward_returns),
                corpus_name=learner_family,
                run_at=datetime.now(),
            )

        # 2. Compute empirical MI between z_t and realised returns
        mi_actual = self._compute_mi(z_matrix, forward_returns)

        # 3. Permutation null: shuffle forward_returns N times
        null_mi_values: list[float] = []
        rng = np.random.default_rng(42)
        for _ in range(self.N_PERMUTATIONS):
            shuffled = rng.permutation(forward_returns)
            null_mi_values.append(self._compute_mi(z_matrix, shuffled))

        null_mi = np.array(null_mi_values)
        mi_null_mean = float(np.mean(null_mi))
        mi_null_std = float(np.std(null_mi))

        # 4. Two-sided z-test using the error function (standard library, no new dep)
        import math

        z_stat = (mi_actual - mi_null_mean) / (mi_null_std + 1e-12)
        # Normal CDF via erf: Φ(x) = 0.5 * erfc(-x / √2)
        p_value = 2.0 * (0.5 * math.erfc(abs(z_stat) / math.sqrt(2)))

        passes = bool(
            p_value < self.ALPHA
            and mi_actual > mi_null_mean
            and z_stat > 1.96  # one-sided equivalent at 0.05
        )

        return LearnabilityProbeResult(
            probe_id=str(uuid.uuid4()),
            z_dim=z_dim,
            mi_actual=float(mi_actual),
            mi_null_mean=mi_null_mean,
            mi_null_std=mi_null_std,
            z_statistic=float(z_stat),
            p_value=float(p_value),
            passes=passes,
            min_observations_required=self.MIN_OBSERVATIONS,
            observation_count=len(forward_returns),
            corpus_name=learner_family,
            run_at=datetime.now(),
        )

    async def _realised_return_for_state(
        self,
        state: LatentStateRecord,
        horizon: int,
    ) -> float:
        """Compute realised forward return from the fabric.

        Uses SPY (or configured market proxy) as the market-level return
        benchmark for z_t learnability. Queries with PIT discipline:
        as_of = period_end + 1 day to get the closing price active at
        period_end.
        """
        start_date = state.pit.period_end
        end_date = start_date + timedelta(days=horizon)
        try:
            start_records = await self._reader.read_price(
                self._market_proxy,
                start_date + timedelta(days=1),
                lookback_days=horizon + 5,
            )
            end_records = await self._reader.read_price(
                self._market_proxy,
                end_date + timedelta(days=1),
                lookback_days=horizon + 5,
            )
        except Exception:
            return float("nan")
        if not start_records or not end_records:
            return float("nan")
        start_rec = start_records[-1]
        end_rec = end_records[-1]
        start_close = start_rec.close
        end_close = end_rec.close
        if start_close is None or end_close is None or start_close <= 0 or end_close <= 0:
            return float("nan")
        return (end_close - start_close) / start_close

    def _compute_mi(self, z: np.ndarray, r: np.ndarray, n_bins: int = 10) -> float:
        """Compute empirical mutual information between z columns and returns.

        Uses histogram-based binning for the continuous variables.
        """
        if len(z) == 0 or len(r) == 0:
            return 0.0

        # Discretize returns into quantile bins
        r_bins = np.percentile(r, np.linspace(0, 100, n_bins + 1))
        r_disc = np.digitize(r, r_bins[1:-1], right=True)

        # Mutual information: I(Z; R) = H(R) - H(R | Z)
        # H(R) — marginal entropy of returns
        r_probs = np.bincount(r_disc, minlength=n_bins) / len(r)
        r_probs = r_probs[r_probs > 0]
        h_r = -np.sum(r_probs * np.log2(r_probs))

        # H(R | Z) — conditional entropy given z
        h_r_given_z = 0.0
        for i in range(z.shape[1]):
            z_col = z[:, i]
            z_bins = np.percentile(z_col, np.linspace(0, 100, n_bins + 1))
            z_disc = np.digitize(z_col, z_bins[1:-1], right=True)
            for j in range(n_bins):
                mask = z_disc == j
                if mask.sum() > 0:
                    r_in_bin = r_disc[mask]
                    probs = np.bincount(r_in_bin, minlength=n_bins) / mask.sum()
                    probs = probs[probs > 0]
                    if len(probs) > 0:
                        h_r_given_z -= (mask.sum() / len(r)) * np.sum(probs * np.log2(probs))

        return max(0.0, h_r - h_r_given_z)
