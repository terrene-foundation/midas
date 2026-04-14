# M03 — Representation Learner Pool

**Spec anchors:** 04, 05.
**Framework:** Kailash ML (primary), Kailash Align (for any LoRA fine-tune paths).
**Depends on:** M00 (T-00-02 learnability probe), M01, M02.

## T-03-01 — Model registry backbone

**Objective:** Kailash ML `ModelRegistry` configured for Midas — versioning, lineage, metric snapshots, promotion state, training-window metadata.
**Invariants:** every model version carries (train window, val window, config hash, parent version, pool layer, status).
**Acceptance:** write and retrieve a version; lineage graph renders.

## T-03-02 — Pre-training corpus ingestion

**Objective:** ingest the pre-training corpus named in T-00-02 into a dedicated fabric namespace. If foundation-model fine-tuning path is chosen, download + version the base checkpoint.
**Acceptance:** corpus loaded, row counts match, sample batch retrievable.

## T-03-03 — SSL-transformer champion candidate

**Objective:** one representation-learner architecture (self-supervised transformer family) as initial champion. Multi-task aux losses per `specs/04- §4`.
**Scope:** 1 architecture, not the full pool — other pool members land as separate todos (T-03-04 to T-03-08).
**Acceptance:** training job runs, checkpoint saved, learnability probe passes per T-00-02.

## T-03-04 — Contrastive encoder challenger

**Objective:** contrastive/InfoNCE encoder as challenger in the same pool.
**Acceptance:** training runs; probe pass.

## T-03-05 — Masked autoencoder challenger

**Objective:** MAE over cross-sectional snapshots + temporal windows.
**Acceptance:** training runs; probe pass.

## T-03-06 — VAE challenger (explicit posterior)

**Objective:** VAE for explicit posterior structure.
**Acceptance:** training runs; probe pass.

## T-03-07 — Deep state-space challenger (S4 / Mamba / Kalman-NN)

**Objective:** one deep SSM variant.
**Acceptance:** training runs; probe pass.

## T-03-08 — Foundation TS model fine-tune challenger

**Objective:** fine-tune one foundation TS model (Chronos / TimesFM / Moirai) on Midas fabric.
**Acceptance:** LoRA/full fine-tune runs via Kailash Align; probe pass.

## T-03-09 — Representation-learner online inference service

**Objective:** daily + active-session inference producing `z_t` posterior candidates from every pool member.
**Invariants:** PIT discipline maintained at inference; no future-data leakage.
**Depends on:** M04.

## T-03-10 — Latent-dim hyperparameter sweep

**Objective:** population-based training over latent-dim in {8, 16, 24, 32}; meta-router scores downstream loss as a function of dim.
**Depends on:** M06.

## T-03-11 — Denoising + robustness audit

**Objective:** Tier 2 tests that representation is stable under (a) corrupted inputs, (b) held-out vol regimes, (c) shuffled temporal order.
**Acceptance:** champion passes all three audits.

**Gate out:** at least two pool members pass the learnability probe, are in the registry with a full lineage, and write `z_t` candidates to `latent_state` table.
