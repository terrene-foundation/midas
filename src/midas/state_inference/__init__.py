"""
M04 State Inference Pool — posterior maintenance, Bayesian filtering,
OOD detection, changepoint detection, and posterior combination.

Ref: specs/04-latent-first-architecture.md SS2-3
Ref: T-04-01 through T-04-06
"""

from midas.state_inference.bayesian_filter import (
    DeepBayesianFilter,
    NeuralKalmanChallenger,
    NormalizingFlowChallenger,
)
from midas.state_inference.changepoint import ChangePointDetector
from midas.state_inference.ood_detector import OODDetector, OODResult
from midas.state_inference.posterior_combination import PosteriorCombination
from midas.state_inference.posterior_service import PosteriorMaintenanceService

__all__ = [
    "ChangePointDetector",
    "DeepBayesianFilter",
    "NeuralKalmanChallenger",
    "NormalizingFlowChallenger",
    "OODDetector",
    "OODResult",
    "PosteriorCombination",
    "PosteriorMaintenanceService",
]
