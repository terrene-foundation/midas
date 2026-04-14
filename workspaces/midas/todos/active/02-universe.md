# M02 — Universe Construction

**Spec anchors:** 03 (universe-and-data §1).
**Depends on:** M01.

## T-02-01 — ETF selection engine

**Objective:** algorithmic selection of ETFs per `specs/03- §1.2` criteria (liquidity, AUM, expense, tracking error, overlap, fund age, missing-exposure detection, Ireland UCITS alternatives).
**Invariants:** selection is idempotent given (as_of_date, fabric state); no hardcoded tickers.
**Acceptance:** Tier 2 runs selection for 2020 and 2024 as-of dates; results differ appropriately; audit trail matches.

## T-02-02 — S&P 1500 filter pipeline

**Objective:** filter current S&P 1500 constituents by liquidity floor, price floor, fundamentals availability, halt history. v1.1 scope but wire infrastructure now.
**Acceptance:** Tier 2 filters a sample universe and produces expected count.

## T-02-03 — Holdings overlap analyzer

**Objective:** compute pairwise ETF holdings overlap; dedupe when >80% per `specs/03- §1.2`.
**Acceptance:** Tier 1 on synthetic ETFs with known overlap returns expected dedupe.

## T-02-04 — Factor gap detector

**Objective:** run factor regression on current universe; identify missing exposures; surface candidate adds.
**Acceptance:** Tier 1 on synthetic universe missing value factor surfaces value-ETF candidates.

## T-02-05 — Universe changelog writer

**Objective:** every add/remove writes to `universe_changelog` with reason, backtest-impact estimate, timestamp.
**Acceptance:** end-to-end add/remove produces a complete log row.

## T-02-06 — Universe review scheduler

**Objective:** monthly ETF review, quarterly full re-eval, quarterly S&P 1500 rebalance window scan.
**Depends on:** M14.

## T-02-07 — Universe constraint enforcement (compliance input)

**Objective:** feed the PACT compliance `env.universe` rule — any proposed trade outside the current universe is blocked.
**Depends on:** M12.

**Gate out:** universe snapshots reproducibly from two different dates; changelog full; scheduler heartbeats.
