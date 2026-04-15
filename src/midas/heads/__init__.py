"""
M05 Model Heads — all prediction heads for the latent-first architecture.

Exports return TS/XS, volatility, tail-risk, allocation, and execution heads.
"""

from midas.heads.return_ts import (
    MambaChallenger,
    ReturnTSHead,
    TCNChallenger,
    TransformerChallenger,
)

__all__ = [
    # Return time-series
    "ReturnTSHead",
    "TCNChallenger",
    "TransformerChallenger",
    "MambaChallenger",
    # Cross-sectional
    "CNNChampion",
    "GNNChallenger",
    "XSTransformerChallenger",
    # Volatility
    "VolHeadChampion",
    "DeepGARCHChallenger",
    # Tail risk
    "NormalizingFlowTailChampion",
    "QuantileDLChallenger",
    "ScoreBasedChallenger",
    # Allocation
    "CVaRPPOChampion",
    "SACChallenger",
    "TD3Challenger",
    "RiskAwareRLChallenger",
    "DecisionTransformerChallenger",
    "MVOBaseline",
    "BlackLittermanBaseline",
    "HRPBaseline",
    "RiskParityBaseline",
    # Execution
    "CostAwareRLChampion",
    "LinearImpactBaseline",
]


# Lazy imports for heads that depend on numpy/scipy
def __getattr__(name):
    if name == "VolHeadChampion":
        from midas.heads.volatility import VolHeadChampion

        return VolHeadChampion
    if name == "DeepGARCHChallenger":
        from midas.heads.volatility import DeepGARCHChallenger

        return DeepGARCHChallenger
    if name == "NormalizingFlowTailChampion":
        from midas.heads.tail_risk import NormalizingFlowTailChampion

        return NormalizingFlowTailChampion
    if name == "QuantileDLChallenger":
        from midas.heads.tail_risk import QuantileDLChallenger

        return QuantileDLChallenger
    if name == "ScoreBasedChallenger":
        from midas.heads.score_tail import ScoreBasedChallenger

        return ScoreBasedChallenger
    if name == "CNNChampion":
        from midas.heads.cross_sectional import CNNChampion

        return CNNChampion
    if name == "GNNChallenger":
        from midas.heads.cross_sectional import GNNChallenger

        return GNNChallenger
    if name == "XSTransformerChallenger":
        from midas.heads.cross_sectional import XSTransformerChallenger

        return XSTransformerChallenger
    if name == "CVaRPPOChampion":
        from midas.heads.allocation import CVaRPPOChampion

        return CVaRPPOChampion
    if name in (
        "SACChallenger",
        "TD3Challenger",
        "RiskAwareRLChallenger",
        "DecisionTransformerChallenger",
    ):
        from midas.heads import allocation as alloc_mod

        return getattr(alloc_mod, name)
    if name in ("MVOBaseline", "BlackLittermanBaseline", "HRPBaseline", "RiskParityBaseline"):
        from midas.heads import allocation as alloc_mod

        return getattr(alloc_mod, name)
    if name == "CostAwareRLChampion":
        from midas.heads.execution import CostAwareRLChampion

        return CostAwareRLChampion
    if name == "LinearImpactBaseline":
        from midas.heads.execution import LinearImpactBaseline

        return LinearImpactBaseline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
