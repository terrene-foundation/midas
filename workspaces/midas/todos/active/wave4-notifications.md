# Wave 4 — Make It Complete

GAP-5 (Notification System, MEDIUM)

**Session estimate:** 1 session
**Spec anchors:** 09 (surfaces and attention — notification tiering, attention budget)

---

## GROUP H: Notification System (GAP-5)

**Current state:** `apps/web/elements/settings/NotificationPreferences.tsx` exists as barrel export but is not rendered on Settings page. No notification backend endpoints. No browser push permission flow. No regime-change toast. No weekly attention summary.

### BUILD Todos

**B10-BE. Build NotificationRouter backend endpoints**

- Create `src/midas/api/notification_routes.py` with `NotificationRouter`: GET `/notifications/preferences` (returns user's tier config + quiet hours + ceiling), PUT `/notifications/preferences` (validates + persists), GET `/notifications/attention-report` (aggregates from `attention_budget_tracker.py` data for the past 7 days). Wire into main FastAPI app.
- **Spec:** 09 S3 (attention budget), S7 (notifications)
- **LOC:** ~150 load-bearing
- **Invariants:** (1) Preferences have defaults (matching spec 09 S7.1 tier mapping). (2) Quiet hours validated: start != end. (3) Ceiling in [5, 120] minutes. (4) Attention report reads from existing `BudgetTracker` data.
- **Dependencies:** None

**B10. Build notification types and query hooks**

- Add to `apps/web/lib/types.ts`: `NotificationPreferences` (tiers per band, quiet_hours, daily_attention_ceiling_minutes), `NotificationTier` (`"silent_in_app" | "standard_push" | "prominent_push_haptic" | "emergency"`), `AttentionReport` (decision_seconds, decision_count, avg_time_to_decide, notification_volume_by_tier, fatigue_signal, override_rate).
- Create `apps/web/lib/queries/useNotifications.ts`: `useNotificationPreferences()` (GET), `useUpdateNotificationPreferences()` (mutation, PUT), `useAttentionReport()` (GET, staleTime: 60s).
- **Spec:** 09 S3 (attention budget), S7 (notifications)
- **LOC:** ~50 load-bearing
- **Invariants:** (1) Tier values match backend `DEFAULT_TIERS` exactly. (2) Update mutation invalidates `["notification-preferences"]` on success. (3) `useAttentionReport` uses 60s staleTime.
- **Dependencies:** None

**B11. Build NotificationPermissionRequest element**

- Create `apps/web/elements/notifications/NotificationPermissionRequest.tsx`. Client component requesting browser push permission via `Notification.requestPermission()`. Three states: (a) default — show request button, (b) granted — green checkmark, (c) denied — muted text with browser settings instructions. Persist in localStorage. Shown after onboarding + in Settings.
- **Spec:** 09 S7.1
- **LOC:** ~50 load-bearing
- **Invariants:** (1) Never calls `requestPermission()` more than once per mount. (2) No browser support → render nothing (graceful no-op). (3) Permission state read from `Notification.permission` on mount.
- **Dependencies:** None

**B12. Build RegimeChangeToast element**

- Create `apps/web/elements/notifications/RegimeChangeToast.tsx`. Subscribes to `useRegimeStore` for band transitions (useEffect with previous-value comparison). Positioned toast top-right showing: new band name + color, one-line description per band, auto-dismiss 5s. Crisis toasts require manual dismissal. Debounce 500ms for rapid transitions.
- **Spec:** 09 S2 (regime-adaptive reshape), S7.1 (notification tier by band)
- **LOC:** ~60 load-bearing
- **Invariants:** (1) Only fires on actual transitions, not initial load. (2) Auto-dismiss 5s (except Crisis). (3) Calm-to-Calm suppressed. (4) Rapid transitions show only latest (debounce 500ms).
- **Dependencies:** None (reads existing regime-store)

**B13. Build WeeklyAttentionSummary element**

- Create `apps/web/elements/notifications/WeeklyAttentionSummary.tsx`. Uses `useAttentionReport()`. Displays: total decision time, decision count, avg time-to-decide, override rate, notification volume by tier (4 bars), fatigue signal (gold warning badge if present). Loading skeleton state. Handles empty (all zeros) with dashes.
- **Spec:** 09 S3.1, S3.3
- **LOC:** ~60 load-bearing
- **Invariants:** (1) Loading skeleton while fetching. (2) Empty report shows dashes. (3) Fatigue signal uses gold warning matching `FatigueWarning.tsx` style.
- **Dependencies:** B10

**B14. Build notifications elements index.tsx**

- Barrel export for `NotificationPermissionRequest`, `RegimeChangeToast`, `WeeklyAttentionSummary`.
- **LOC:** ~5
- **Dependencies:** B11, B12, B13

### WIRE Todos

**W4. Wire NotificationPreferences to real backend**

- Refactor `NotificationPreferences.tsx` from props-only (`initialPreferences`, `onSave`) to direct `useNotificationPreferences()` for data + `useUpdateNotificationPreferences()` for save. Map boolean toggles to tier strings per band. Backend GET/PUT `/notifications/preferences`.
- **Spec:** 09 S7.1, S3.3
- **Verification:** (1) Load Settings → shows saved preferences (or defaults). (2) Toggle + Save → persists. (3) Reload → shows saved. (4) Invalid input → backend 400.
- **Dependencies:** B10

**W5. Wire NotificationPermissionRequest into onboarding + Settings**

- Add to two locations: (a) ActivateStep's "done" state (after onboarding), (b) Settings page between Attention Report and KillSwitchPanel (only if not yet granted).
- **Spec:** 09 S7.1
- **Verification:** (1) Complete onboarding → permission request visible. (2) Click Allow → browser prompt. (3) After granting → "Notifications enabled". (4) Settings → hidden if already granted.
- **Dependencies:** B11

**W6. Wire RegimeChangeToast into shell layout**

- Add `<RegimeChangeToast />` to `apps/web/app/(shell)/layout.tsx` inside flex container. Absolutely positioned, reads from existing `useRegimeStore`.
- **Spec:** 09 S2, S7.1
- **Verification:** (1) Load `/pulse` Calm → no toast on initial load. (2) Band change → toast with correct name + color. (3) Auto-dismiss 5s (unless Crisis). (4) Rapid changes → latest only.
- **Dependencies:** B12

**W7. Wire WeeklyAttentionSummary into Settings page**

- Add `<WeeklyAttentionSummary />` section in Settings between Attention Report and KillSwitchPanel.
- **Spec:** 09 S3.1, S3.3, S9.4
- **Verification:** (1) Settings page shows summary. (2) Loading skeleton while fetching. (3) No decisions → dashes. (4) With decisions → correct counts. (5) Fatigue → gold warning.
- **Dependencies:** B13

**W8. Wire NotificationPreferences section into Settings page**

- Add "Notification Preferences" section to Settings page after Attention Report, before KillSwitchPanel. Component wired via W4, then placed.
- **Spec:** 09 S3.3, S9.4
- **Verification:** (1) Settings shows preferences. (2) Change + Save persists. (3) "Saved!" confirmation. (4) Reload shows updated.
- **Dependencies:** W4

---

## Execution Order

B10 → B11, B12, B13 (parallel) → B14 → W4 → W5, W6, W7, W8 (parallel)

All fits in 1 session. Can pair with Wave 2 GROUP F (ModelRegistry) if that group didn't complete in its own session.

**Note:** Backend notification endpoints (`/notifications/preferences`, `/notifications/attention-report`) are assumed to exist or be built as part of this wave. If they don't exist yet, add a small backend todo: create `NotificationRouter` with GET/PUT preferences and GET attention-report, seeded from `attention_budget_tracker.py` data.
