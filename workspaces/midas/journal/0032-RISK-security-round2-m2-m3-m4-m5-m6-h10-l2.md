---
type: RISK
date: 2026-04-22
created_at: 2026-04-22T06:50:15.428Z
author: co-authored
session_id: fd9df422-9e85-464d-a92e-edcfcc6afcc1
project: midas
topic: Security findings M2/M3/M4/M5/M6/H10/L2 resolved
phase: redteam
tags: [security, midas, auth, pydantic, ibkr, cors, tests]
---

# RISK: Security round 2 — M2/M3/M4/M5/M6/H10/L2 resolved

**Commit**: `8c626fb` — fix(midas): resolve red team security findings M2/M3/M4/M5/M6/H10/L2

## Findings resolved

| ID  | Severity | Issue                                                                            | Fix                                                                                |
| --- | -------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| M2  | MED      | DEBUG log level defaulted to `true` — sensitive data in logs                     | Changed to `false`                                                                 |
| M3  | MED      | SQLite unencrypted — no dev-mode notice in config.py                             | Added dev-only note                                                                |
| M4  | HIGH     | Fernet weak-key pattern detection missing in `CredentialStore.__init__`          | Added detection                                                                    |
| M5  | HIGH     | IBKR queue exception propagation via `asyncio.Future` instead of `asyncio.Event` | Fixed to use `asyncio.Event`                                                       |
| M6  | CRIT     | Pydantic request body validation absent on all 10 endpoint signatures            | Added validation; handlers updated from `.get()` dict access to `.field` attribute |
| H10 | LOW      | CORS already correct — no changes needed                                         | N/A (confirmed correct)                                                            |
| L2  | MED      | No security regression suite                                                     | Added 34 tests in `tests/security/`                                                |

## What was most risky

**M6** (Pydantic validation) was the highest risk — all 10 endpoint handlers used `.get()` dict access instead of typed `.field` access, meaning malformed or missing fields would silently pass through without validation. This is the primary injection vector for type-confusion attacks on the API surface.

**M5** (IBKR queue) was the highest operational risk — `asyncio.Future` vs `asyncio.Event` means exceptions in the IBKR message handler could silently fail to propagate, causing orders to appear to succeed while the error was swallowed.

## What unlocked the fix

These findings were surfaced during a `/redteam` security audit round. The round was triggered by the wave-based todo system (Wave 3: Make It Trustworthy, GAP-2: IBKR Order States + Rejection Taxonomy).

## Verification

```
tests/security/ ... 34 passed
```

## Related

- Commits: `8c626fb` (round 2 fixes), `a3ab53e` (M8 field allowlist follow-up)
- Source: `workspaces/midas/04-validate/security-audit.md`
