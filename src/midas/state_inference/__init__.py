"""
M04 State Inference Pool — posterior maintenance, Bayesian filtering,
OOD detection, changepoint detection, and posterior combination.

Layer relationship with midas.ml:
  - midas.ml/ood_detector: z-score based OOD with internal state store
  - midas.state_inference/ood_detector: Mahalanobis distance OOD (state_inference is canonical)
  - midas.ml/posterior_state: Kalman filter with fabric reader/writer adapter
  - midas.state_inference/posterior_service: DataFlow-backed service with cache
  - midas.ml/deep_bayesian_filter: MLP gain estimator for Kalman updates
  - midas.state_inference/bayesian_filter: GRU-based nn.Module filter architectures

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
