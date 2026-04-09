# User Flow: Daily Monitoring (Calm Markets)

## Trigger

User opens app or glances at widget during normal market conditions.

## Goal

User confirms "everything is fine" in under 30 seconds and closes app.

---

## Flow

### Glance Path (Widget)

**Widget display**:

```
$2,847,312  +0.4% today
REGIME: Calm
No approvals needed
```

**Decision**: If no pending approvals and regime is calm, user may not even open app. This is success — Midas is working.

### Quick Check Path (App)

**Step 1: Pulse Screen**

- Regime banner: "Calm" (muted, unobtrusive)
- Portfolio value: large, prominent, with daily and YTD change
- No approval section (hidden when empty)
- Recent actions (last 24-48h):
  ```
  Yesterday  Rebalanced bonds +2%  "Duration tilt for rate outlook"
  2 days ago  Trimmed QQQ 1%       "Sector rotation signal"
  ```
- Market context strip: VIX, SPX, DXY — all in normal ranges

**Step 2 (optional): Tap a recent action**

- Sees one-line rationale expand to structured brief
- Can tap "Debate" to challenge if curious
- Usually doesn't — just confirming AI is sensible

**Step 3: Close app**

---

## Notification Pattern (Calm Markets)

- **Silent in-app**: Routine rebalancing executed, visible in Pulse feed
- **No push notifications** during calm regime unless:
  - Portfolio crosses a significant milestone (e.g., new all-time high)
  - Weekly summary digest (configurable)

## Weekly Summary (Push Notification)

```
Weekly Summary: +1.8% ($50,423)
3 trades executed, $127 in fees
Regime: Calm all week
[View Details]
```

---

## Success Criteria

- User time in app: < 30 seconds on a calm day
- User confidence: "Midas is handling things, nothing needs my attention"
- Zero unnecessary notifications during calm periods
