# M21 — Release & CI/CD & Deployment

**Spec anchors:** rules/deployment.md.
**Depends on:** M17, M18, M19, M20.

## T-21-01 — Monorepo structure

**Objective:** `src/` backend, `apps/web/`, `apps/mobile/`, `docs/`, `specs/`, `deploy/`.
**Acceptance:** `pyproject.toml` + workspace config + iOS/Android builds all green.

## T-21-02 — CI pipeline (GitHub Actions)

**Objective:** per-PR: Tier 1 unit + lint + security-scan; on main: Tier 2 integration + Tier 3 E2E + coverage check.
**Acceptance:** CI passes on clean main.

## T-21-03 — Pre-commit hooks

**Objective:** format + lint + secret scan + leakage-check fast; blocks on zero-tolerance violations.

## T-21-04 — Docker / container build

**Objective:** Nexus backend + scheduler + workers containerized; reproducible builds.
**Acceptance:** `docker compose up` runs end-to-end locally.

## T-21-05 — Deployment target (v1 = local + single VPS)

**Objective:** provisioning script for single VPS (PostgreSQL + Redis + Nexus API + scheduler + worker + web app); documented in `deploy/`.
**Acceptance:** end-to-end deploy from clean VPS to running system.

## T-21-06 — Mobile app store prep (iOS TestFlight + Android internal)

**Objective:** signing, metadata, internal-track distribution; no public store release for v1 (personal tool).

## T-21-07 — Monitoring + alerting

**Objective:** observability via OpenTelemetry (per Core SDK); dashboards for job heartbeats, IBKR health, model calibration drift, compliance vetoes.
**Acceptance:** one operator dashboard exists.

## T-21-08 — Backup + disaster recovery

**Objective:** encrypted PostgreSQL backups daily; weekly offsite; documented restore procedure; restore smoke-tested quarterly.

## T-21-09 — Release gate checklist

**Objective:** blocking checklist per `rules/agents.md` — reviewer + security-reviewer + gold-standards-validator must pass before release.

## T-21-10 — Documentation

**Objective:** README, architecture notes, operator runbook, user guide (non-technical), disaster-recovery playbook.

**Gate out:** production-like deploy reachable; monitoring alive; backup tested; release checklist clean.
