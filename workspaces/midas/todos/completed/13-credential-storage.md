# M13 — Credential Storage & API Security

**Spec anchors:** 11 §6.
**Depends on:** M01.

## T-13-01 — `credentials` table with Fernet encryption

**Objective:** encrypted storage for IBKR OAuth tokens, Perplexity key, EODHD key, etc.; key from `.env`.
**Invariants:** tokens never logged; log redaction enforced in adapters.
**Acceptance:** Tier 2 confirms logs do not contain raw token; decryption round-trips.

## T-13-02 — Token refresh background job

**Objective:** scheduled refresh for IBKR OAuth tokens; audit entry per refresh.
**Depends on:** M14.

## T-13-03 — Nexus JWT authentication middleware

**Objective:** JWT auth on every Nexus endpoint; session management with inactivity timeout.
**Acceptance:** Tier 2 unauthorized call returns 401.

## T-13-04 — Biometric re-auth for high-stakes mobile actions

**Objective:** mobile app invokes Face ID / fingerprint before trade approvals, envelope widening, kill-switch clear, paper→live.
**Depends on:** M18.

## T-13-05 — CORS + rate limiting

**Objective:** restrictive CORS + per-session/IP rate limits.
**Acceptance:** Tier 2 confirms.

## T-13-06 — Secrets lifecycle in deployment

**Objective:** `.env` in `.gitignore`; `.env.example` template; production secrets-manager plan documented.
**Acceptance:** CI secret-scan passes; `.env.example` tracks all required keys.

## T-13-07 — Credential-decode null-byte protection

**Objective:** shared helper per `rules/security.md` §"Credential Decode Helpers" — null-byte rejection on every credential decode site.
**Acceptance:** regression test per `rules/security.md` passes.

**Gate out:** auth on all endpoints, credentials encrypted and rotation working, no raw secrets in logs, rate limits active.
