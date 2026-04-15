"""Tier 1 unit tests for M05 Model Heads.

Each test verifies output shapes, value ranges, and interface contracts.
All neural-network heads use torch; classical baselines use numpy.
"""

import numpy as np
import pytest
import torch

from midas.heads import (
    BlackLittermanBaseline,
    CNNChampion,
    CVaRPPOChampion,
    CostAwareRLChampion,
    DecisionTransformerChallenger,
    DeepGARCHChallenger,
    GNNChallenger,
    HRPBaseline,
    LinearImpactBaseline,
    MambaChallenger,
    MVOBaseline,
    NormalizingFlowTailChampion,
    QuantileDLChallenger,
    ReturnTSHead,
    RiskAwareRLChallenger,
    RiskParityBaseline,
    SACChallenger,
    ScoreBasedChallenger,
    TD3Challenger,
    TCNChallenger,
    TransformerChallenger,
    VolHeadChampion,
    XSTransformerChallenger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rand_batch(dim1, dim2=None, dim3=None):
    """Return a random float32 tensor of the requested shape."""
    if dim3 is not None:
        return torch.randn(dim1, dim2, dim3)
    if dim2 is not None:
        return torch.randn(dim1, dim2)
    return torch.randn(dim1)


# ===================================================================
# Return Time-Series Heads
# ===================================================================


class TestReturnTSHead:
    """ReturnTSHead champion tests."""

    def test_output_is_dict_keyed_by_horizon(self):
        model = ReturnTSHead(z_dim=16, hidden_dim=64, horizons=[21, 63, 126])
        z_t = _rand_batch(4, 16)
        out = model(z_t)
        assert isinstance(out, dict)
        assert set(out.keys()) == {21, 63, 126}

    def test_per_horizon_output_is_mean_and_logvar(self):
        model = ReturnTSHead(z_dim=16, hidden_dim=64, horizons=[21, 63, 126])
        z_t = _rand_batch(4, 16)
        out = model(z_t)
        for h in [21, 63, 126]:
            mean, log_var = out[h]
            assert mean.shape == (4,)
            assert log_var.shape == (4,)

    def test_different_horizons_produce_different_outputs(self):
        model = ReturnTSHead(z_dim=16, hidden_dim=64, horizons=[21, 126])
        z_t = _rand_batch(4, 16)
        out = model(z_t)
        mean_21, _ = out[21]
        mean_126, _ = out[126]
        assert not torch.allclose(mean_21, mean_126)

    def test_custom_horizons(self):
        model = ReturnTSHead(z_dim=16, hidden_dim=32, horizons=[5, 10])
        z_t = _rand_batch(2, 16)
        out = model(z_t)
        assert set(out.keys()) == {5, 10}
        for h in [5, 10]:
            mean, log_var = out[h]
            assert mean.shape == (2,)
            assert log_var.shape == (2,)


class TestTCNChallenger:
    """TCN-family challenger tests."""

    def test_output_matches_return_ts_interface(self):
        model = TCNChallenger(z_dim=16, hidden_dim=64, horizons=[21, 63, 126])
        z_t = _rand_batch(4, 16)
        out = model(z_t)
        assert isinstance(out, dict)
        assert set(out.keys()) == {21, 63, 126}
        for h in [21, 63, 126]:
            mean, log_var = out[h]
            assert mean.shape == (4,)
            assert log_var.shape == (4,)

    def test_single_horizon(self):
        model = TCNChallenger(z_dim=16, hidden_dim=32, horizons=[21])
        z_t = _rand_batch(3, 16)
        out = model(z_t)
        assert set(out.keys()) == {21}
        mean, log_var = out[21]
        assert mean.shape == (3,)
        assert log_var.shape == (3,)


class TestTransformerChallenger:
    """iTransformer/PatchTST challenger tests."""

    def test_output_matches_return_ts_interface(self):
        model = TransformerChallenger(
            z_dim=16, hidden_dim=64, horizons=[21, 63, 126], n_heads=4, n_layers=2
        )
        z_t = _rand_batch(4, 16)
        out = model(z_t)
        assert isinstance(out, dict)
        assert set(out.keys()) == {21, 63, 126}
        for h in [21, 63, 126]:
            mean, log_var = out[h]
            assert mean.shape == (4,)
            assert log_var.shape == (4,)


class TestMambaChallenger:
    """S4/Mamba-style challenger tests."""

    def test_output_matches_return_ts_interface(self):
        model = MambaChallenger(z_dim=16, hidden_dim=64, horizons=[21, 63, 126])
        z_t = _rand_batch(4, 16)
        out = model(z_t)
        assert isinstance(out, dict)
        assert set(out.keys()) == {21, 63, 126}
        for h in [21, 63, 126]:
            mean, log_var = out[h]
            assert mean.shape == (4,)
            assert log_var.shape == (4,)


# ===================================================================
# Cross-Sectional Heads
# ===================================================================


class TestCNNChampion:
    """CNN cross-sectional champion tests."""

    def test_output_shape_is_scores_per_asset(self):
        n_assets = 50
        model = CNNChampion(n_assets=n_assets, feature_dim=32, hidden_dim=64)
        features = _rand_batch(4, n_assets, 32)
        scores = model(features)
        assert scores.shape == (4, n_assets)

    def test_scores_are_real_valued(self):
        model = CNNChampion(n_assets=10, feature_dim=8, hidden_dim=16)
        features = _rand_batch(2, 10, 8)
        scores = model(features)
        assert torch.isfinite(scores).all()

    def test_different_asset_counts(self):
        model = CNNChampion(n_assets=20, feature_dim=16, hidden_dim=32)
        features = _rand_batch(3, 20, 16)
        scores = model(features)
        assert scores.shape == (3, 20)


class TestGNNChallenger:
    """Graph neural network challenger tests."""

    def test_output_shape_with_adjacency(self):
        n_assets = 10
        model = GNNChallenger(n_assets=n_assets, feature_dim=16, hidden_dim=32)
        features = _rand_batch(4, n_assets, 16)
        adj = torch.eye(n_assets).unsqueeze(0).expand(4, -1, -1)
        scores = model(features, adj)
        assert scores.shape == (4, n_assets)

    def test_output_is_finite(self):
        n_assets = 10
        model = GNNChallenger(n_assets=n_assets, feature_dim=16, hidden_dim=32)
        features = _rand_batch(2, n_assets, 16)
        adj = torch.eye(n_assets).unsqueeze(0).expand(2, -1, -1)
        scores = model(features, adj)
        assert torch.isfinite(scores).all()


class TestXSTransformerChallenger:
    """Cross-sectional transformer challenger tests."""

    def test_output_shape(self):
        n_assets = 30
        model = XSTransformerChallenger(n_assets=n_assets, feature_dim=16, hidden_dim=64, n_heads=4)
        features = _rand_batch(4, n_assets, 16)
        scores = model(features)
        assert scores.shape == (4, n_assets)

    def test_output_is_finite(self):
        model = XSTransformerChallenger(n_assets=10, feature_dim=8, hidden_dim=16, n_heads=2)
        features = _rand_batch(2, 10, 8)
        scores = model(features)
        assert torch.isfinite(scores).all()


# ===================================================================
# Volatility Heads
# ===================================================================


class TestVolHeadChampion:
    """DL-hybrid vol posterior champion tests."""

    def test_output_is_mean_and_log_variance(self):
        model = VolHeadChampion(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        vol_mean, vol_log_var = model(z_t)
        assert vol_mean.shape == (4,)
        assert vol_log_var.shape == (4,)

    def test_vol_mean_is_positive(self):
        """After softplus activation, vol mean should be strictly positive."""
        model = VolHeadChampion(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(8, 16)
        vol_mean, _ = model(z_t)
        assert (vol_mean > 0).all(), "Vol mean must be positive (softplus output)"

    def test_different_batch_sizes(self):
        model = VolHeadChampion(z_dim=16, hidden_dim=32)
        z_t = _rand_batch(1, 16)
        vol_mean, vol_log_var = model(z_t)
        assert vol_mean.shape == (1,)
        assert vol_log_var.shape == (1,)


class TestDeepGARCHChallenger:
    """GARCH-family hybrid challenger tests."""

    def test_output_shape_with_realized_vol(self):
        model = DeepGARCHChallenger(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        realized_vol = _rand_batch(4, 1)
        vol_mean, vol_log_var = model(z_t, realized_vol)
        assert vol_mean.shape == (4,)
        assert vol_log_var.shape == (4,)

    def test_vol_mean_is_positive(self):
        model = DeepGARCHChallenger(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        realized_vol = torch.rand(4, 1) + 0.01
        vol_mean, _ = model(z_t, realized_vol)
        assert (vol_mean > 0).all()


# ===================================================================
# Tail Risk Heads
# ===================================================================


class TestNormalizingFlowTailChampion:
    """NF-based tail posterior champion tests."""

    def test_output_is_mean_and_log_variance(self):
        model = NormalizingFlowTailChampion(z_dim=16, hidden_dim=64, n_flows=4)
        z_t = _rand_batch(4, 16)
        tail_mean, tail_log_var = model(z_t)
        assert tail_mean.shape == (4,)
        assert tail_log_var.shape == (4,)

    def test_output_is_finite(self):
        model = NormalizingFlowTailChampion(z_dim=16, hidden_dim=64, n_flows=4)
        z_t = _rand_batch(4, 16)
        tail_mean, tail_log_var = model(z_t)
        assert torch.isfinite(tail_mean).all()
        assert torch.isfinite(tail_log_var).all()


class TestQuantileDLChallenger:
    """Quantile DL challenger tests."""

    def test_output_is_dict_keyed_by_quantile(self):
        quantiles = [0.01, 0.05, 0.10]
        model = QuantileDLChallenger(z_dim=16, hidden_dim=64, quantiles=quantiles)
        z_t = _rand_batch(4, 16)
        out = model(z_t)
        assert isinstance(out, dict)
        assert set(out.keys()) == set(quantiles)

    def test_per_quantile_output_shape(self):
        quantiles = [0.01, 0.05, 0.10]
        model = QuantileDLChallenger(z_dim=16, hidden_dim=64, quantiles=quantiles)
        z_t = _rand_batch(4, 16)
        out = model(z_t)
        for q in quantiles:
            assert out[q].shape == (4,), f"Quantile {q} should have shape (4,)"

    def test_custom_quantiles(self):
        quantiles = [0.025, 0.975]
        model = QuantileDLChallenger(z_dim=16, hidden_dim=32, quantiles=quantiles)
        z_t = _rand_batch(2, 16)
        out = model(z_t)
        assert set(out.keys()) == {0.025, 0.975}
        for q in quantiles:
            assert out[q].shape == (2,)


class TestScoreBasedChallenger:
    """Score-based tail challenger tests."""

    def test_output_is_mean_and_log_variance(self):
        model = ScoreBasedChallenger(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        tail_mean, tail_log_var = model(z_t)
        assert tail_mean.shape == (4,)
        assert tail_log_var.shape == (4,)


# ===================================================================
# Allocation Policy Heads
# ===================================================================


class TestCVaRPPOChampion:
    """CVaR-aware PPO policy net tests."""

    def test_output_is_target_weights(self):
        n_assets = 10
        model = CVaRPPOChampion(z_dim=16, n_assets=n_assets, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        positions = _rand_batch(4, n_assets)
        envelope = _rand_batch(4, 1)
        weights = model(z_t, positions, envelope)
        assert weights.shape == (4, n_assets)

    def test_weights_are_non_negative(self):
        """Softmax output is always non-negative."""
        n_assets = 10
        model = CVaRPPOChampion(z_dim=16, n_assets=n_assets, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        positions = _rand_batch(4, n_assets)
        envelope = _rand_batch(4, 1)
        weights = model(z_t, positions, envelope)
        assert (weights >= 0).all()

    def test_weights_sum_to_one(self):
        """Softmax output sums to 1 per batch."""
        n_assets = 10
        model = CVaRPPOChampion(z_dim=16, n_assets=n_assets, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        positions = _rand_batch(4, n_assets)
        envelope = _rand_batch(4, 1)
        weights = model(z_t, positions, envelope)
        sums = weights.sum(dim=1)
        assert torch.allclose(sums, torch.ones(4), atol=1e-5)


class TestSACChallenger:
    """SAC allocation challenger tests."""

    def test_output_shape(self):
        n_assets = 10
        model = SACChallenger(z_dim=16, n_assets=n_assets, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        positions = _rand_batch(4, n_assets)
        weights = model(z_t, positions)
        assert weights.shape == (4, n_assets)

    def test_weights_sum_to_one(self):
        n_assets = 10
        model = SACChallenger(z_dim=16, n_assets=n_assets, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        positions = _rand_batch(4, n_assets)
        weights = model(z_t, positions)
        sums = weights.sum(dim=1)
        assert torch.allclose(sums, torch.ones(4), atol=1e-5)


class TestTD3Challenger:
    """TD3 allocation challenger tests."""

    def test_output_shape(self):
        n_assets = 10
        model = TD3Challenger(z_dim=16, n_assets=n_assets, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        positions = _rand_batch(4, n_assets)
        weights = model(z_t, positions)
        assert weights.shape == (4, n_assets)

    def test_weights_sum_to_one(self):
        n_assets = 10
        model = TD3Challenger(z_dim=16, n_assets=n_assets, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        positions = _rand_batch(4, n_assets)
        weights = model(z_t, positions)
        sums = weights.sum(dim=1)
        assert torch.allclose(sums, torch.ones(4), atol=1e-5)


class TestRiskAwareRLChallenger:
    """Risk-aware RL challenger tests."""

    def test_output_shape(self):
        n_assets = 10
        model = RiskAwareRLChallenger(z_dim=16, n_assets=n_assets, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        positions = _rand_batch(4, n_assets)
        weights = model(z_t, positions)
        assert weights.shape == (4, n_assets)

    def test_weights_sum_to_one(self):
        n_assets = 10
        model = RiskAwareRLChallenger(z_dim=16, n_assets=n_assets, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        positions = _rand_batch(4, n_assets)
        weights = model(z_t, positions)
        sums = weights.sum(dim=1)
        assert torch.allclose(sums, torch.ones(4), atol=1e-5)


class TestDecisionTransformerChallenger:
    """Decision Transformer for regime transfer tests."""

    def test_output_shape(self):
        n_assets = 10
        model = DecisionTransformerChallenger(z_dim=16, n_assets=n_assets, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        positions = _rand_batch(4, n_assets)
        weights = model(z_t, positions)
        assert weights.shape == (4, n_assets)

    def test_weights_sum_to_one(self):
        n_assets = 10
        model = DecisionTransformerChallenger(z_dim=16, n_assets=n_assets, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        positions = _rand_batch(4, n_assets)
        weights = model(z_t, positions)
        sums = weights.sum(dim=1)
        assert torch.allclose(sums, torch.ones(4), atol=1e-5)


# ===================================================================
# Classical Baselines
# ===================================================================


class TestMVOBaseline:
    """Mean-Variance Optimization baseline tests."""

    def test_weights_sum_to_one(self):
        n = 5
        expected_returns = np.array([0.10, 0.12, 0.08, 0.15, 0.09])
        cov = np.eye(n) * 0.04
        optimizer = MVOBaseline()
        w = optimizer.optimize(expected_returns, cov, risk_aversion=1.0)
        assert w.shape == (n,)
        assert np.isclose(w.sum(), 1.0, atol=1e-6), f"Weights sum to {w.sum()}"

    def test_weights_are_non_negative(self):
        n = 5
        expected_returns = np.array([0.10, 0.12, 0.08, 0.15, 0.09])
        cov = np.eye(n) * 0.04
        optimizer = MVOBaseline()
        w = optimizer.optimize(expected_returns, cov, risk_aversion=1.0)
        assert (w >= -1e-8).all(), f"Negative weights found: {w}"

    def test_higher_return_gets_higher_weight(self):
        """With diagonal covariance, higher expected return should get higher weight."""
        n = 3
        expected_returns = np.array([0.05, 0.10, 0.20])
        cov = np.eye(n) * 0.04
        optimizer = MVOBaseline()
        w = optimizer.optimize(expected_returns, cov, risk_aversion=1.0)
        assert w[2] > w[0], "Asset 3 (highest return) should get highest weight"

    def test_risk_aversion_affects_weights(self):
        """Higher risk aversion should shift towards equal weights."""
        n = 3
        expected_returns = np.array([0.05, 0.10, 0.20])
        cov = np.eye(n) * 0.04
        optimizer = MVOBaseline()
        w_low = optimizer.optimize(expected_returns, cov, risk_aversion=0.5)
        w_high = optimizer.optimize(expected_returns, cov, risk_aversion=5.0)
        # Low risk aversion should concentrate more on high-return asset
        assert w_low[2] > w_high[2] or np.abs(w_low[2] - w_high[2]) < 1e-4


class TestBlackLittermanBaseline:
    """Black-Litterman baseline tests."""

    def test_weights_sum_to_one(self):
        n = 3
        prior_returns = np.array([0.08, 0.06, 0.10])
        cov = np.eye(n) * 0.04
        views = np.array([[1.0, 0.0, 0.0]])  # Asset 1 outperforms
        confidences = np.array([0.8])
        optimizer = BlackLittermanBaseline()
        w = optimizer.optimize(prior_returns, cov, views, confidences)
        assert w.shape == (n,)
        assert np.isclose(w.sum(), 1.0, atol=1e-6), f"Weights sum to {w.sum()}"

    def test_positive_view_shifts_weight(self):
        """A positive view on an asset should increase its weight vs prior."""
        n = 2
        prior_returns = np.array([0.05, 0.05])
        cov = np.eye(n) * 0.04
        # View: asset 0 will return 10%
        views = np.array([[1.0, 0.0]])
        confidences = np.array([0.9])
        optimizer = BlackLittermanBaseline()
        w = optimizer.optimize(prior_returns, cov, views, confidences)
        assert w[0] > w[1], "Positive view on asset 0 should increase its weight"


class TestHRPBaseline:
    """Hierarchical Risk Parity baseline tests."""

    def test_weights_sum_to_one(self):
        n = 5
        cov = np.eye(n) * 0.04
        np.fill_diagonal(cov, [0.01, 0.02, 0.03, 0.04, 0.05])
        optimizer = HRPBaseline()
        w = optimizer.optimize(cov)
        assert w.shape == (n,)
        assert np.isclose(w.sum(), 1.0, atol=1e-6), f"Weights sum to {w.sum()}"

    def test_weights_are_positive(self):
        n = 5
        cov = np.eye(n) * 0.04
        optimizer = HRPBaseline()
        w = optimizer.optimize(cov)
        assert (w > 0).all(), f"Non-positive weights found: {w}"

    def test_lower_risk_gets_higher_weight(self):
        """Assets with lower variance should get higher weight."""
        n = 3
        cov = np.diag([0.01, 0.04, 0.09])
        optimizer = HRPBaseline()
        w = optimizer.optimize(cov)
        assert w[0] > w[2], "Lowest-risk asset should get highest weight"


class TestRiskParityBaseline:
    """Risk Parity baseline tests."""

    def test_weights_sum_to_one(self):
        n = 4
        cov = np.diag([0.01, 0.04, 0.09, 0.16])
        optimizer = RiskParityBaseline()
        w = optimizer.optimize(cov)
        assert w.shape == (n,)
        assert np.isclose(w.sum(), 1.0, atol=1e-6), f"Weights sum to {w.sum()}"

    def test_weights_are_positive(self):
        n = 4
        cov = np.diag([0.01, 0.04, 0.09, 0.16])
        optimizer = RiskParityBaseline()
        w = optimizer.optimize(cov)
        assert (w > 0).all(), f"Non-positive weights found: {w}"

    def test_equal_risk_contribution(self):
        """Risk parity should produce approximately equal marginal risk contributions."""
        n = 3
        cov = np.diag([0.01, 0.04, 0.09])
        optimizer = RiskParityBaseline()
        w = optimizer.optimize(cov)
        # Marginal risk contribution: w_i * (cov @ w)_i / sqrt(w^T cov w)
        sigma_w = np.sqrt(w @ cov @ w)
        mrc = w * (cov @ w) / sigma_w
        # All contributions should be approximately equal
        assert np.allclose(mrc, mrc.mean(), atol=0.05), f"Risk contributions not equal: {mrc}"


# ===================================================================
# Execution Heads
# ===================================================================


class TestCostAwareRLChampion:
    """Cost-aware RL champion for execution tests."""

    def test_output_is_size_and_timing(self):
        model = CostAwareRLChampion(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(4, 16)
        order_params = _rand_batch(4, 3)  # e.g., size, urgency, remaining
        venue_features = _rand_batch(4, 5)  # e.g., spread, depth, etc.
        size_frac, timing_score = model(z_t, order_params, venue_features)
        assert size_frac.shape == (4,)
        assert timing_score.shape == (4,)

    def test_size_fraction_is_bounded(self):
        """Size fraction should be between 0 and 1 (sigmoid output)."""
        model = CostAwareRLChampion(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(8, 16)
        order_params = _rand_batch(8, 3)
        venue_features = _rand_batch(8, 5)
        size_frac, _ = model(z_t, order_params, venue_features)
        assert (size_frac >= 0).all() and (size_frac <= 1).all()

    def test_timing_score_is_bounded(self):
        """Timing score should be between 0 and 1 (sigmoid output)."""
        model = CostAwareRLChampion(z_dim=16, hidden_dim=64)
        z_t = _rand_batch(8, 16)
        order_params = _rand_batch(8, 3)
        venue_features = _rand_batch(8, 5)
        _, timing_score = model(z_t, order_params, venue_features)
        assert (timing_score >= 0).all() and (timing_score <= 1).all()


class TestLinearImpactBaseline:
    """Classical Almgren-Chriss impact model tests."""

    def test_output_is_scalar(self):
        model = LinearImpactBaseline()
        impact = model.estimate_impact(
            order_size=1000.0,
            avg_volume=100000.0,
            volatility=0.2,
        )
        assert isinstance(impact, float)

    def test_larger_order_more_impact(self):
        """Larger order should produce larger impact."""
        model = LinearImpactBaseline()
        impact_small = model.estimate_impact(order_size=100.0, avg_volume=100000.0, volatility=0.2)
        impact_large = model.estimate_impact(
            order_size=10000.0, avg_volume=100000.0, volatility=0.2
        )
        assert impact_large > impact_small

    def test_higher_vol_more_impact(self):
        """Higher volatility should produce larger impact."""
        model = LinearImpactBaseline()
        impact_low = model.estimate_impact(order_size=1000.0, avg_volume=100000.0, volatility=0.1)
        impact_high = model.estimate_impact(order_size=1000.0, avg_volume=100000.0, volatility=0.4)
        assert impact_high > impact_low

    def test_larger_volume_less_impact(self):
        """Larger average volume should produce less impact."""
        model = LinearImpactBaseline()
        impact_thin = model.estimate_impact(order_size=1000.0, avg_volume=50000.0, volatility=0.2)
        impact_thick = model.estimate_impact(order_size=1000.0, avg_volume=200000.0, volatility=0.2)
        assert impact_thin > impact_thick

    def test_positive_impact(self):
        """Impact should always be non-negative."""
        model = LinearImpactBaseline()
        impact = model.estimate_impact(order_size=1000.0, avg_volume=100000.0, volatility=0.2)
        assert impact >= 0.0
