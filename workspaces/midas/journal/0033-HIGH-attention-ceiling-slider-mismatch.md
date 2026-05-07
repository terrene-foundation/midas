# 0033-HIGH-attention-ceiling-slider-mismatch.md

**Type:** RISK
**Date:** 2026-05-06
**Wave:** Wave 4 — Notification System

## Finding

Frontend `NotificationPreferences` attention ceiling slider allowed values up to 960 minutes (16 hours), but the backend `NotificationRouter.update_preferences` enforces `[5, 120]` minutes. A user could set a value the backend would reject.

## Root Cause

The slider was copied from an earlier version that used a different range. The backend validation was implemented correctly; the frontend was not updated to match.

## Fix

Updated `NotificationPreferences.tsx` slider:
- `min={5}` (was `60`)
- `max={120}` (was `960`)
- `step={5}` (was `30`)
- Labels updated: "5m" / "2h" (was "1h" / "16h")

## Prevention

Added to redteam round 1 (Wave 4). Rule: frontend affordance ranges MUST match backend `[ui-backend-defense.md]` validation bounds before wire todo is marked complete.

## Related

- `specs/09-surfaces-and-attention.md` S3.3
- `src/midas/api/routes_extended.py` line 411
