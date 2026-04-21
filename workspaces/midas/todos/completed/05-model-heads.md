# M05 — Model Heads

**Spec anchors:** 04 §6, 05.
**Depends on:** M03, M04.

## T-05-01 — Return time-series head — champion

**Objective:** one TS return predictor conditioned on `z_t` as initial champion. Multi-horizon (1/3/6 month) outputs with posteriors.
**Invariants:** output is a distribution, not a point; PIT training.
**Acceptance:** calibration curve tracked; learnability probe passes.

## T-05-02 — Return TS head — challenger architectures

**Objective:** three challengers — TCN family, transformer family (iTransformer/PatchTST/Crossformer), Mamba/S4.
**Acceptance:** all three in registry + shadow runs.

## T-05-03 — Return cross-sectional head — CNN champion

**Objective:** CNN over cross-sectional universe as the spatial ranker for security selection.
**Acceptance:** information-coefficient metric tracked; passes learnability probe.

## T-05-04 — Return cross-sectional head — GNN challenger

**Objective:** graph neural network over asset-relationship graphs (correlation, co-holding, sector, supply-chain).
**Acceptance:** registry + shadow.

## T-05-05 — Return cross-sectional head — transformer challenger

**Objective:** cross-sectional transformer with ticker-level attention.
**Acceptance:** registry + shadow.

## T-05-06 — Volatility head — DL-hybrid champion

**Objective:** continuous vol posterior conditioned on `z_t` + realized-vol transformer variant.
**Acceptance:** quantile calibration tracked.

## T-05-07 — Volatility head — deep-GARCH challenger

**Objective:** GARCH-family hybrid.
**Acceptance:** registry + shadow.

## T-05-08 — Tail-risk head — normalizing-flow champion

**Objective:** normalizing-flow-based tail posterior.
**Acceptance:** tail-hit-rate calibration tracked.

## T-05-09 — Tail-risk head — quantile-DL and score-based challengers

**Objective:** two challengers.
**Acceptance:** registry + shadow.

## T-05-10 — Allocation policy — DRL champion (CVaR-PPO)

**Objective:** CVaR-aware PPO policy net as initial DRL champion for SAA / TAA allocation.
**Invariants:** policy reads `z_t` + current positions + envelope; outputs target weights.
**Acceptance:** offline-RL training on historical trajectories converges; shadow P&L positive over walk-forward.

## T-05-11 — Allocation policy — SAC / TD3 / risk-aware RL challengers

**Objective:** three DRL challengers.
**Acceptance:** registry + shadow.

## T-05-12 — Allocation policy — classical baselines (MVO / BL / HRP / RP)

**Objective:** four classical optimizers as baseline challengers — not champions. MVO, Black-Litterman, Hierarchical Risk Parity, Risk Parity.
**Invariants:** classical outputs enter the router on equal footing with DRL but do not by default drive decisions.
**Acceptance:** all four in registry + shadow.

## T-05-13 — Allocation policy — offline-RL and meta-RL (Decision Transformer)

**Objective:** Decision Transformer + offline-RL variant for regime transfer.
**Acceptance:** registry + shadow.

## T-05-14 — Execution head — cost-aware RL

**Objective:** order-sizing + timing bandit over IBKR venue constraints. Feeds the execution agent.
**Acceptance:** simulated execution cost beats static TWAP/VWAP baseline.

## T-05-15 — Execution head — linear impact baseline

**Objective:** classical impact model as execution-head challenger.
**Acceptance:** registry + shadow.

## T-05-16 — Per-head calibration pipeline

**Objective:** every head registered emits predictions that are scored against outcomes; calibration curves stored per `(head, z_t neighborhood, horizon)` per T-00-04.
**Invariants:** Holm-Bonferroni corrected significance tests; minimum-sample gate.
**Acceptance:** Tier 2 test with noise-heads confirms zero false promotions.
**Depends on:** T-00-04.

## T-05-17 — Embedding pool (multiple text encoders)

**Objective:** multiple text embedding candidates run per-document and are tracked by the router.
**Depends on:** M09.

**Gate out:** each of returns (TS + XS), vol, tail, allocation, execution has at least one champion + at least two challengers in the registry with shadow P&L tracking and calibration curves.
