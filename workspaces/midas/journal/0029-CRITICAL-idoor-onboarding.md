# CRITICAL: IDOR in OnboardingRouter — Unauthenticated State Mutation

**Date:** 2026-04-27
**Round:** Round 13 red team
**Severity:** CRITICAL

## Finding

`OnboardingRouter._resolve_user()` at `routes_extended.py:44-50` falls back to `body.get("user_id")` when no JWT is present:

```python
def _resolve_user(request: Request, body: dict[str, Any]) -> str:
    jwt_user = getattr(request.state, "user", None)
    if jwt_user and jwt_user.get("sub"):
        return str(jwt_user["sub"])
    return str(body.get("user_id") or "default")  # ← IDOR vector
```

None of the onboarding endpoints have auth middleware. An unauthenticated attacker can:

- Read/modify any user's onboarding state via `user_id` in request body
- Connect a brokerage to any user's flow
- Set risk profiles on behalf of other users
- Activate paper trading for other users

## Impact

Any unauthenticated request to the onboarding API can mutate any user's state.

## Spec Coverage

- Spec 08 § Auth: onboarding requires authenticated user context
- Spec 02 § Front office onboarding surface

## Resolution Path

1. Add auth middleware to all onboarding write endpoints, OR
2. Remove the `body.get("user_id")` fallback — require JWT auth
3. Add security test for onboarding IDOR

## Status

**RESOLVED** — Fix committed.

- `OnboardingRouter._resolve_user()` removed `body.get("user_id")` fallback
- `PaperLiveRouter._resolve_user()` same fix applied
- Both now raise `HTTPException(401, "Authentication required")` when no JWT
- Same fix pattern applied to `PaperLiveRouter._resolve_user()` at line 968
