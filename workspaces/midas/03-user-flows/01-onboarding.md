# User Flow: Onboarding

## Trigger

New user signs up or installs Midas for the first time.

## Goal

User has a connected brokerage, configured risk parameters, and understands what Midas will do — within 10 minutes.

---

## Flow

### Step 1: Welcome & Identity

**Screen**: Welcome
**Content**: "Midas is your AI investment co-pilot. It manages your portfolio systematically, explains every decision, and asks before acting in uncertain markets."
**Action**: Continue

### Step 2: Connect Brokerage

**Screen**: Brokerage Connection
**Content**: "Connect your Interactive Brokers account. Midas needs read access to see your positions and write access to execute approved trades."
**Actions**:

- Connect IBKR (OAuth 2.0 flow via IBKR Web API v1.0)
- Manual setup (API key + secret)
  **Validation**: Test connection, show account balance and current positions
  **Error state**: Connection failed — show specific IBKR error, retry option

### Step 3: Import Current Portfolio

**Screen**: Portfolio Review
**Content**: "Here's what you currently hold. Midas will use this as the starting point."
**Display**: Current positions with values, allocation percentages
**Action**: Confirm / "This isn't right" (troubleshooting)

### Step 4: Risk Profile

**Screen**: Risk Configuration
**Content**: "How much risk are you comfortable with? This determines how aggressively Midas invests."

**Questions** (visual sliders + plain language):

1. **Maximum drawdown tolerance**
   - "If your portfolio drops from its peak, at what point should Midas start protecting capital?"
   - Slider: 10% / 15% / 20% / 25% / 30%
   - Default: 20%

2. **Volatility comfort**
   - "How much daily movement is acceptable?"
   - Low (bank-like, 5-8% annual) / Medium (balanced, 10-15%) / High (aggressive, 15-25%) / Very High (maximum growth, 20%+)
   - Default: High

3. **Concentration limit**
   - "Should Midas spread your money widely or concentrate in top opportunities?"
   - Max 5% per position / Max 10% / Max 15% / Max 20%
   - Default: 15%

4. **Autonomy level**
   - "When should Midas ask for your approval?"
   - Always ask (every trade) / Ask for large moves (>5% of portfolio) / Ask only in turbulent markets / Full autonomy
   - Default: Ask for large moves

**Important note displayed after Step 4**: "These are starting points. Midas will begin adapting these parameters to market conditions immediately — tightening risk limits when danger signals appear, relaxing them when opportunities are strong. You can always override Midas's adaptive decisions."

### Step 5: Investment Universe Constraints

**Screen**: Universe Constraints (SPEC-01 FP-2: data-driven, not human-curated)
**Content**: "Midas will algorithmically select the best instruments for your portfolio based on expense ratios, correlations, and exposure coverage. Are there any asset classes you want to exclude?"
**Exclusion toggles** (all INCLUDED by default — user opts OUT, not in):

- Exclude emerging markets? (No)
- Exclude commodities? (No)
- Exclude REITs? (No)
- Exclude high-yield/corporate bonds? (No)
  **Note**: "Midas will also evaluate Ireland-domiciled UCITS ETFs for dividend tax efficiency (relevant for Singapore residents holding US instruments)."
  **Action**: Confirm constraints → Midas runs algorithmic universe construction

### Step 6: Data Sources

**Screen**: Data Configuration
**Content**: "Midas needs market data to make decisions. We'll set up your data sources."
**Auto-configured**:

- EODHD (from .env API key)
- Yahoo Finance (backup, no key needed)
  **Optional**:
- Perplexity API for news/sentiment (from .env, or skip)
  **Validation**: Test each data source, show status

### Step 7: Review & Activate

**Screen**: Summary
**Content**: "Here's your Midas configuration. Ready to start paper trading?"
**Display**:

- Connected account + balance
- Risk profile summary (plain language, with note: "These are starting points — Midas adapts automatically")
- Universe constraints
- Approval threshold
- "Midas will begin a mandatory 2-week paper trading period to validate all systems before any real money is at risk."
  **Actions**: Start Paper Trading / Go back and adjust

### Step 8: Paper Trading Period (SPEC-01 FP-7 — Mandatory)

**Screen**: Paper Trading Dashboard (modified Pulse)
**Duration**: Minimum 2 weeks. User cannot skip.
**Content**: "Midas is running in paper trading mode. All decisions are simulated — no real trades are executed."
**Visual indicator**: Persistent "PAPER TRADING" banner across all screens (distinct color, unmissable).

**What happens during paper trading**:

- Full strategy engine runs: signals, optimization, risk management, regime detection
- Decisions are generated and shown as if real (user can approve/reject/debate)
- Trades are simulated against IBKR paper trading account
- All subsystems are validated: data pipeline, signal generation, optimization, risk checks, execution path, approval workflow

**Paper Trading Report** (generated at end of 2-week period):

- Subsystem health: pass/fail checklist (data, signals, optimizer, risk, execution, approvals, regime)
- Simulated P&L and risk metrics
- Any anomalies or warnings encountered
- Comparison to backtest expectations (is live behavior consistent with backtested?)

**Transition to Live**:

- User reviews paper trading report
- Explicit action: "Go Live" button (appears only after minimum 2 weeks AND clean report)
- Biometric confirmation required
- "PAPER TRADING" banner replaced with normal Pulse

### Step 9: First Live Briefing (async)

**Screen**: Pulse (loading state)
**Content**: "Midas is now live. Analyzing your portfolio and current market conditions..."
**Progress**: Show what it's doing (scanning positions, assessing regime, building target allocation)
**Completion**: Transition to first Pulse view with initial analysis and any recommended actions

---

## Edge Cases

- **Empty IBKR account**: Skip portfolio import, go straight to "Midas will start building your portfolio from cash"
- **Large existing portfolio**: "You have 47 positions. Midas will analyze each one and may suggest consolidation to improve efficiency. This takes longer."
- **No EODHD key**: Block activation — data source is required
- **No Perplexity key**: Allow activation — news/sentiment is optional, show degraded capability notice
- **IBKR connection drops during setup**: Save progress, allow resume

## Success Criteria

- Time to complete setup: < 10 minutes (paper trading starts immediately after)
- User understands: what Midas will do, when it will ask permission, that risk parameters adapt, that paper trading is mandatory
- System has: brokerage connection, risk seed parameters, universe constraints, data sources
- Paper trading validates: all 7 subsystems pass before live trading is allowed
