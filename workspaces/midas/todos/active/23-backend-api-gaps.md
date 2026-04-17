# M23 — Backend API Gaps for Web Frontend

**Spec anchors:** 07 (debate resolution, decision modify), 08 (autonomy, paper-live), 09 (notifications, attention budget, surfaces), 10 (paper-live transition, approval tap), 14 (IBKR connection).
**Framework:** Nexus (HTTP + WebSocket), DataFlow (persisted state).
**Depends on:** M10 (brief composer), M17 (web app structure), existing routes at `src/midas/api/routes.py`.
**Parent:** M17-01 (Nexus API backbone).

The existing backend at `src/midas/api/routes.py` exposes eight routers (Pulse, Decisions, Debate, Portfolio, Backtest, Signal, Settings, Compliance) plus Health and Audit. All use `get_fabric()` for data. The frontend requires nine categories of missing capability, organized below by domain.

---

## Group A: Authentication and Sessions

### T-23-01 — JWT Auth System (login, refresh, logout)

**Objective:** Replace static API key with per-user JWT authentication. Three endpoints: login (email/password -> access + refresh tokens), refresh (rotate access token), logout (invalidate refresh token). JWT middleware on all `/api/v1/*` routes except health. Session tracking in DataFlow `sessions` table.

**Spec refs:** 08 S1 (trust boundary -- user-owned parameters), 09 S9.4 (settings surface requires identity).
**Estimated LOC:** ~400 (router + middleware + session model + tests).

**Endpoints:**

- `POST /api/v1/auth/login` -- validate credentials, return `{access_token, refresh_token, expires_in}`
- `POST /api/v1/auth/refresh` -- accept refresh token, return new access token
- `POST /api/v1/auth/logout` -- invalidate refresh token, record logout in audit log

**DataFlow models:**

- `users` (id, email, password_hash, created_at)
- `sessions` (id, user_id, refresh_token_hash, created_at, expires_at, revoked_at)

**Acceptance:**

1. Login with valid credentials returns JWT; invalid credentials returns 401 with generic message (no email enumeration).
2. Refresh token rotation: old refresh token is invalidated on use, new pair returned.
3. Logout revokes the refresh token; subsequent refresh calls return 401.
4. All existing `/api/v1/*` routes return 401 without a valid JWT; `/health`, `/live`, `/ready` are exempt.
5. Structured logging at every auth event (login, refresh, logout, rejection).
6. Tests cover: valid login, invalid password, expired token refresh, revoked token refresh, unauthenticated route access, exempt route access.

---

## Group B: Real-Time Transport

### T-23-02 — WebSocket Endpoint with Channel Subscription

**Objective:** FastAPI WebSocket at `/ws` supporting channel-based subscriptions. Channels: `regime_change`, `price_update`, `decision_new`, `decision_executed`, `debate_message`. Connection accepts a `subscribe` message with a list of channels; server pushes JSON events on subscribed channels. Heartbeat every 30s; connection drops after two missed heartbeats.

**Spec refs:** 09 S2 (regime-adaptive reshape needs real-time a_t), 09 S6 (Pulse updates), 09 S7 (decision notifications), 09 S8 (debate messages).
**Estimated LOC:** ~350 (WebSocket handler + channel registry + broadcast service + tests).

**Protocol:**

```
Client -> Server: {"action": "subscribe", "channels": ["regime_change", "decision_new"]}
Client -> Server: {"action": "ping"}
Server -> Client: {"action": "pong"}
Server -> Client: {"channel": "regime_change", "data": {"a_t": 0.72, "band": "elevated"}}
Server -> Client: {"channel": "decision_new", "data": {"id": "...", "type": "rebalance", ...}}
```

**Acceptance:**

1. Client connects, subscribes to channels, receives events only on subscribed channels.
2. Unsubscribed channels produce no messages to that connection.
3. Heartbeat: server sends ping, client must respond within 60s or connection is dropped.
4. Max 10 concurrent connections per user (configurable).
5. Structured logging on connect, disconnect, subscribe, and publish events.
6. Tests cover: subscribe/unsubscribe, cross-channel isolation, heartbeat timeout, max connection enforcement.

---

## Group C: Onboarding Flow

### T-23-03 — Onboarding Endpoints

**Objective:** Four-step onboarding sequence for new users: brokerage connection test, risk profile seeding, universe constraint setup, and paper-trading activation. Each step persists state and validates prior steps completed.

**Spec refs:** 08 S2.1 (L0 Observer default on install), 10 S3 (paper-live gate), 14 S2 (IBKR transport), 08 S1 (trust boundary -- universe exclusions are user-owned).
**Estimated LOC:** ~350 (router + validation + state machine + tests).

**Endpoints:**

- `POST /api/v1/onboarding/connect-brokerage` -- test IBKR connection (paper endpoint), store credentials reference, return connection status
- `POST /api/v1/onboarding/risk-profile` -- accept risk parameters (vol target band, drawdown ceiling, concentration caps), validate against envelope bounds
- `POST /api/v1/onboarding/universe-constraints` -- set exclusions (asset classes, sectors, instruments)
- `POST /api/v1/onboarding/activate` -- start paper trading; gates on prior three steps complete

**DataFlow models:**

- `onboarding_state` (user_id, step, brokerage_connected, risk_profile_set, universe_set, activated_at)

**Acceptance:**

1. Each step validates the prior step completed; returns 409 with missing step if out of order.
2. Brokerage connection test does NOT store raw credentials -- stores a reference ID only.
3. Risk profile validates: vol_target_low < vol_target_high, drawdown_ceiling in (0.05, 0.30), concentration caps in (0.01, 0.50).
4. Activate fails if paper trading account is already active (idempotent).
5. Audit log entry on each step completion.
6. Tests cover: sequential happy path, out-of-order rejection, invalid risk parameters, double-activate idempotency.

---

## Group D: Decision Enhancement

### T-23-04 — Decision Modify Endpoint

**Objective:** Allow the user to modify parameters of a pending decision (quantity, price, allocation weight) and have the system recalculate consequences. This is the API behind user flow 03 Step 3b -- the "modify" button on the Decisions surface that lets the user adjust before approving.

**Spec refs:** 07 S3.3 (`recompute_with_constraint` tool), 09 S7 (decision cards with modify affordance), 10 S2 (spatial separation of approve/modify/reject).
**Estimated LOC:** ~300 (endpoint + recalculation logic + tests).

**Endpoint:**

- `PATCH /api/v1/decisions/{id}/modify` -- accept parameter changes, recalculate brief sections (consequences, cost estimates, risk impact), return updated decision

**Request body:**

```json
{
  "parameter_overrides": { "quantity": 50, "limit_price": 185.0 },
  "reason": "Reduce position size to stay within sector cap"
}
```

**Response:** Updated decision with recalculated `if_approved` and `if_rejected` sections, updated cost estimate, updated risk metrics.

**Acceptance:**

1. Only pending decisions can be modified; approved/declined/executed decisions return 409.
2. Modified decision retains original decision_id with a `version` increment.
3. Modification reason is persisted in audit log with the parameter diff.
4. Recalculated consequences include updated cost estimates and portfolio risk impact.
5. If modification would violate compliance rules, return 422 with the specific rule violation.
6. Tests cover: valid modification, non-pending rejection, compliance-violating modification, version tracking.

---

### T-23-05 — Debate Resolution Endpoint

**Objective:** Resolve a debate thread into one of four states defined in spec 07 S3.5. Resolution persists the outcome, updates the linked decision (if applicable), and records the resolution in the audit log.

**Spec refs:** 07 S3.5 (resolution states), 07 S3.6 (thread memory), 09 S8 (debate surface).
**Estimated LOC:** ~250 (endpoint + state machine + audit + tests).

**Endpoint:**

- `PATCH /api/v1/debate/threads/{id}/resolve` -- accept resolution state and optional metadata

**Resolution states:**
| State | Required fields | Side effect |
|---|---|---|
| `decision_updated` | `updated_decision_id`, `parameter_changes` | Links thread to updated decision |
| `decision_maintained` | (none) | Thread closed, decision unchanged |
| `open` | `note` | Thread left open for resumption |
| `envelope_change_proposed` | `proposed_envelope_changes` | Routes to envelope adjustment flow |

**Acceptance:**

1. Only valid resolution states accepted; invalid states return 422.
2. `decision_updated` requires a pending decision linked to the thread.
3. `envelope_change_proposed` creates a pending envelope change request visible in Settings.
4. Resolved threads are immutable -- no further messages can be added.
5. Resolution writes an audit log entry with thread_id, state, and all required fields.
6. Tests cover: each resolution state, invalid state rejection, resolved thread immutability, missing required fields.

---

## Group E: Notification and Attention

### T-23-06 — Notification Preferences and Attention Report

**Objective:** Two endpoints -- one for reading/writing notification tier preferences (per band, quiet hours), one for generating a weekly attention usage report. The notification config drives the push notification behavior defined in 09 S7.

**Spec refs:** 09 S3.3 (attention is a user setting), 09 S7 (notification tiering by band).
**Estimated LOC:** ~300 (router + preferences model + report generation + tests).

**Endpoints:**

- `GET /api/v1/settings/notifications` -- return current notification preferences
- `PUT /api/v1/settings/notifications` -- update preferences (per-band tiers, quiet hours, daily attention ceiling)
- `GET /api/v1/settings/attention-report` -- return weekly attention usage report

**Notification preferences model:**

```json
{
  "tiers": {
    "calm": "silent_in_app",
    "elevated": "standard_push",
    "urgent": "prominent_push_haptic",
    "crisis": "emergency"
  },
  "quiet_hours": {
    "start": "22:00",
    "end": "07:00",
    "timezone": "Asia/Singapore"
  },
  "daily_attention_ceiling_minutes": 30
}
```

**Attention report fields:**

- decision_seconds_this_week, decision_count, average_time_to_decide
- notification_volume_by_tier, fatigue_signal_present (bool)
- override_rate (fraction of decisions modified or rejected)

**Acceptance:**

1. GET returns current preferences; first call returns defaults from spec 09 S7.
2. PUT validates: quiet_hours start < end, timezone is valid IANA, ceiling in [5, 120] minutes.
3. Attention report aggregates from `audit_log` and `decisions` tables for the past 7 days.
4. Report returns 200 even with zero data (all counters at 0).
5. Tests cover: default preferences, valid update, invalid quiet hours, attention report with and without data.

---

## Group F: Backtest Detail Views

### T-23-07 — Backtest Detail Sub-Endpoints

**Objective:** Four sub-endpoints on the existing BacktestRouter that return the specific detail views the frontend needs for the Backtest surface tabs: scorecard, regime breakdown, consistency, and cost sensitivity. Currently only a monolithic `/results/{run_id}` exists.

**Spec refs:** 09 S9.2 (backtest surface -- scorecard first, equity curve second, regime breakdown, consistency, cost sensitivity).
**Estimated LOC:** ~350 (four endpoints + query logic + tests).

**Endpoints:**

- `GET /api/v1/backtest/{id}/scorecard` -- key metrics (CAGR, Sharpe, max drawdown, Calmar, turnover, win rate)
- `GET /api/v1/backtest/{id}/regime-breakdown` -- performance segmented by historical z_t analogue regimes
- `GET /api/v1/backtest/{id}/consistency` -- sub-horizon (monthly, quarterly) return distribution and positive-period fraction
- `GET /api/v1/backtest/{id}/cost-sensitivity` -- net performance at different cost assumptions (current, 2x, 0.5x, zero-cost)

**Acceptance:**

1. Each endpoint returns 404 for non-existent run_id.
2. Scorecard returns all six metrics; missing metrics return null (not 0) so the frontend can distinguish "not computed" from "zero".
3. Regime breakdown segments by at least 3 regime categories (calm, elevated, crisis equivalent).
4. Consistency returns monthly and quarterly sub-periods.
5. Cost sensitivity returns at least 4 cost scenarios.
6. Tests cover: valid run_id, missing run_id, partially-computed results (some metrics null).

---

## Group G: Paper-to-Live Transition

### T-23-08 — Paper-to-Live Transition Gate

**Objective:** Single endpoint that initiates the paper-to-live transition, enforcing the 2-week minimum paper period and the explicit user confirmation required by specs 08 S2.1 and 10 S3. This is the backend enforcement -- the frontend gate is just UX; the real check happens here.

**Spec refs:** 08 S2.1 (L0 mandatory during paper, 2-week report), 10 S3 (paper-live transition rule), 10 S3.3 (first seven live days at L1).
**Estimated LOC:** ~300 (endpoint + gate checks + state transition + tests).

**Endpoint:**

- `POST /api/v1/settings/paper-live/transition` -- initiate transition; validates all gates

**Gate checks (server-side, not just UI):**

1. Paper trading active for >= 14 calendar days.
2. User has opened the paper-trading report (tracked via `paper_report_viewed_at` timestamp).
3. No open kill switch.
4. No compliance rules currently violated.
5. `user_confirmed` boolean in request body is true.
6. `biometric_confirmed` boolean in request body is true.

**On success:**

- Set mode to `live` in settings.
- Downgrade autonomy to L1 (Co-Pilot) regardless of current level (per 10 S3.3).
- Record transition in audit log with timestamp, prior paper duration, and all gate check results.
- Set `live_start_date` for the 7-day L1 enforcement window.

**Acceptance:**

1. Transition fails with 403 if paper period < 14 days, including the exact days remaining.
2. Transition fails with 403 if report not viewed, kill switch active, or compliance violated.
3. Transition fails with 400 if user_confirmed or biometric_confirmed is false/missing.
4. Successful transition resets autonomy to L1 and records all gate results in audit.
5. Second call after successful transition returns 409 (already live).
6. Tests cover: happy path, each gate failure independently, already-live idempotency.

---

## Group H: Position History

### T-23-09 — Position History Endpoint

**Objective:** Per-ticker position history showing how a position evolved over time -- size changes, cost basis adjustments, P&L snapshots. This backs the "position links to its history" requirement in spec 09 S9.1.

**Spec refs:** 09 S9.1 (each position links to its history and the debate thread that led to its current weight).
**Estimated LOC:** ~250 (endpoint + query + tests).

**Endpoint:**

- `GET /api/v1/portfolio/positions/{ticker}/history` -- return chronological position changes

**Query parameters:**

- `from_date` (optional, ISO 8601, default 30 days ago)
- `to_date` (optional, ISO 8601, default today)
- `limit` (optional, default 100, max 500)

**Response shape:**

```json
{
  "ticker": "NVDA",
  "current_quantity": 150,
  "history": [
    {
      "date": "2026-04-10",
      "action": "buy",
      "quantity_change": 50,
      "price": 185.2,
      "resulting_quantity": 150,
      "cost_basis_change": 9260.0,
      "decision_id": "d-789",
      "debate_thread_id": null
    }
  ],
  "linked_debate_threads": ["t-42"]
}
```

**Acceptance:**

1. Returns 404 if ticker has no position history.
2. History entries are chronological (oldest first).
3. Each entry links to the decision that caused the change (nullable -- some changes may be corporate actions or transfers).
4. Response includes `linked_debate_threads` for any debate threads that influenced this position's history.
5. Date range filtering works; limit is respected.
6. Tests cover: ticker with history, unknown ticker, date filtering, limit enforcement, position with linked debates.

---

## Implementation Order

The groups have the following dependency structure:

```
T-23-01 (Auth)           -- foundational; everything else benefits from identity
  |
  +-- T-23-02 (WebSocket) -- requires auth for connection identity
  +-- T-23-03 (Onboarding) -- requires auth + brokerage config
  |
  +-- T-23-04 (Decision modify)    -- independent after auth
  +-- T-23-05 (Debate resolution)  -- independent after auth
  +-- T-23-06 (Notifications)      -- independent after auth
  +-- T-23-07 (Backtest detail)    -- independent, no auth strictly required
  +-- T-23-08 (Paper-live)         -- depends on onboarding state + auth
  +-- T-23-09 (Position history)   -- independent, no auth strictly required
```

Recommended session order (each fits within one session):

| Session | Todos             | Rationale                                                                  |
| ------- | ----------------- | -------------------------------------------------------------------------- |
| 1       | T-23-01           | Auth is the foundation; all other endpoints benefit from it                |
| 2       | T-23-02 + T-23-09 | WebSocket + position history are independent, similar size                 |
| 3       | T-23-03 + T-23-08 | Onboarding and paper-live share brokerage/state concepts                   |
| 4       | T-23-04 + T-23-05 | Decision modify and debate resolution are both decision-surface extensions |
| 5       | T-23-06 + T-23-07 | Notifications and backtest detail are settings/query surface extensions    |

---

## Notes

- All new routers should follow the existing pattern in `routes.py`: class-based, async, use `get_fabric()`, structured logging on every endpoint.
- The Nexus auth middleware should be registered globally with `exempt_paths` for health endpoints (per Nexus JWTConfig naming convention).
- WebSocket transport goes through Nexus `WebSocketTransport` when available; falls back to raw FastAPI WebSocket when running without Nexus.
- No new external dependencies beyond what Nexus already provides for JWT middleware and WebSocket support.
