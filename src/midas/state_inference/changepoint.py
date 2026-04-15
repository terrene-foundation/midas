"""
BOCPD-style online changepoint detection for regime identification.

Implements Bayesian Online Changepoint Detection (Adams & MacKay 2007)
adapted for financial time series. Maintains a run-length distribution
and flags changepoints when the probability of a run-length reset exceeds
a threshold.

Ref: M04 State Inference Pool specification
Ref: specs/04-latent-first-architecture.md SS3 (regime awareness)
"""

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class ChangePointDetector:
    """Online Bayesian changepoint detector.

    Implements a simplified BOCPD with a Gaussian observation model.
    At each step, the detector maintains a distribution over run lengths
    (how many observations since the last changepoint). A large probability
    mass at run length 0 indicates a likely changepoint.

    Parameters
    ----------
    hazard_rate:
        Constant hazard rate (probability of a changepoint at each step).
        Lower values require stronger evidence to declare a changepoint.
    observation_noise:
        Assumed noise variance in the observation model.
    """

    def __init__(
        self,
        hazard_rate: float = 0.01,
        observation_noise: float = 1.0,
    ) -> None:
        if not (0 < hazard_rate < 1):
            raise ValueError(f"hazard_rate must be in (0, 1), got {hazard_rate}")
        if observation_noise <= 0:
            raise ValueError(f"observation_noise must be positive, got {observation_noise}")
        self._hazard_rate = hazard_rate
        self._obs_noise = observation_noise

        # Run-length distribution: indexed by run length
        # Initialize with run length 0 having probability 1
        self._run_length_probs = np.array([1.0])
        self._time_index = 0

        # Sufficient statistics for each run length
        self._sums = np.array([0.0])  # sum of observations for each run length
        self._sums_sq = np.array([0.0])  # sum of squared observations
        self._counts = np.array([0])  # number of observations

        # History of detected changepoints: (time_index, probability)
        self._changepoints: list[tuple[int, float]] = []

    def _log_predictive_prob(self, x: float, run_length: int) -> float:
        """Compute log predictive probability P(x_t | x_{t-run_length:t-1}).

        Uses a conjugate Normal-Gaussian model with known variance.
        """
        n = self._counts[run_length]
        if n == 0:
            # No data for this run length: use a broad prior
            mu0 = 0.0
            sigma0 = 10.0
        else:
            mu0 = self._sums[run_length] / n
            # Posterior variance shrinks with more data
            sigma0 = np.sqrt(self._obs_noise / n + self._obs_noise)

        # Log probability under Gaussian
        log_prob = -0.5 * np.log(2 * np.pi * sigma0**2) - 0.5 * ((x - mu0) / sigma0) ** 2
        return log_prob

    def update(self, observation: float) -> tuple[bool, float, np.ndarray]:
        """Process a new observation and return changepoint information.

        Parameters
        ----------
        observation:
            The new data point (scalar).

        Returns
        -------
        is_changepoint:
            True if a changepoint was detected at this step.
        probability:
            Probability that a changepoint occurred at this step.
        run_length_distribution:
            Current posterior distribution over run lengths.
        """
        x = float(observation)
        t = self._time_index
        max_run = len(self._run_length_probs)

        # Step 1: Compute predictive probabilities for each run length
        log_preds = np.array([self._log_predictive_prob(x, r) for r in range(max_run)])

        # Step 2: Compute growth probabilities (no changepoint)
        # P(r_t = r + 1 | data) = P(r_{t-1} = r) * P(x_t | r) * (1 - H)
        log_growth = (
            np.log(self._run_length_probs + 1e-300) + log_preds + np.log(1 - self._hazard_rate)
        )

        # Step 3: Compute changepoint probability
        # P(r_t = 0 | data) = sum_r P(r_{t-1} = r) * P(x_t | r) * H
        log_cp = np.logaddexp.reduce(np.log(self._run_length_probs + 1e-300) + log_preds) + np.log(
            self._hazard_rate
        )

        # Step 4: Normalize
        log_joint = np.concatenate([log_cp.reshape(1), log_growth])
        log_joint -= np.logaddexp.reduce(log_joint)  # log-normalize
        new_probs = np.exp(log_joint)

        # Ensure numerical stability
        new_probs = new_probs / new_probs.sum()

        # Extract changepoint probability.
        # BOCPD distributes changepoint evidence across short run lengths
        # (r=0 means CP at this step, r=1 means CP one step ago, etc.).
        # We use the combined mass on short runs (0..2) as the effective
        # changepoint probability — but only once we have enough run lengths
        # for this to be meaningful (at least 4, so short runs are a proper
        # subset rather than "everything").
        min_run_lengths = 4
        if len(new_probs) >= min_run_lengths:
            cp_prob = float(new_probs[:3].sum())
        else:
            cp_prob = float(new_probs[0])

        # Determine if this is a changepoint.
        is_cp = cp_prob > 0.5

        if is_cp:
            self._changepoints.append((t, cp_prob))
            logger.info(
                "changepoint.detected",
                time_index=t,
                probability=cp_prob,
                observation=x,
            )

        # Step 5: Update sufficient statistics
        new_sums = np.zeros(len(new_probs))
        new_sums_sq = np.zeros(len(new_probs))
        new_counts = np.zeros(len(new_probs), dtype=int)

        # Run length 0: new segment starts with this observation only
        new_sums[0] = x
        new_sums_sq[0] = x * x
        new_counts[0] = 1

        # Run lengths > 0: extend previous run lengths
        for r in range(1, len(new_probs)):
            prev_r = r - 1
            if prev_r < len(self._sums):
                new_sums[r] = self._sums[prev_r] + x
                new_sums_sq[r] = self._sums_sq[prev_r] + x * x
                new_counts[r] = self._counts[prev_r] + 1
            else:
                new_sums[r] = x
                new_sums_sq[r] = x * x
                new_counts[r] = 1

        # Commit state
        self._run_length_probs = new_probs
        self._sums = new_sums
        self._sums_sq = new_sums_sq
        self._counts = new_counts
        self._time_index += 1

        logger.debug(
            "changepoint.update",
            time_index=t,
            cp_prob=cp_prob,
            is_cp=is_cp,
            max_run_length=len(new_probs) - 1,
        )

        return is_cp, cp_prob, self._run_length_probs.copy()

    def get_most_likely_changepoints(self) -> list[tuple[int, float]]:
        """Return all detected changepoints as (time_index, probability).

        Returns
        -------
        list of (time_index, probability)
            Each entry is a time step where a changepoint was detected,
            along with the posterior probability of that changepoint.
        """
        return list(self._changepoints)
