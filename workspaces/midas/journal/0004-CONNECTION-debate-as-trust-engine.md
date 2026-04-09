---
type: CONNECTION
date: 2026-04-09
created_at: 2026-04-09T21:30:00+08:00
author: agent
project: midas
topic: The AI debate feature is not just UX — it is the trust calibration mechanism that enables autonomy
phase: analyze
tags: [ai-debate, trust, graduated-autonomy, product-strategy]
---

## Connection

Three independently researched components — the AI debate interface (UX research), the counterfactual tracking system (strategy research), and the graduated autonomy model (value audit) — form a reinforcing loop:

```
Debate → User challenges AI → AI cites evidence
    ↓
Counterfactual tracking → Shows what WOULD have happened
    ↓
Trust calibration → User learns when AI is reliable
    ↓
Graduated autonomy → User opts into higher autonomy
    ↓
Fewer debates needed → System becomes more autonomous
```

The debate feature is not a chatbot bolted onto a trading system. It is the mechanism by which the system earns the right to operate autonomously. Without debate, there is no trust calibration. Without trust calibration, autonomy is unjustified.

## Components Linked

1. **AI Debate Agent** (04-ai-debate-system.md) — the conversation interface
2. **Decision Outcome Tracking** (02-data-layer.md, `decision_outcomes` table) — counterfactual measurement
3. **Override Pattern Detection** (04-ai-debate-system.md, §6) — learning from disagreements
4. **Autonomy Level** (user_settings table, `autonomy_level` field) — the governance control
5. **Onboarding Risk Profile** (01-onboarding.md, Step 4) — initial calibration

## Why This Matters

This connection reframes the product roadmap. The AI debate feature should not be deprioritized as a "nice to have" — it is load-bearing infrastructure for the entire autonomy model. Without it, Midas is just another robo-advisor with a fancier backtest. With it, Midas has a unique trust flywheel that no competitor has built.

The override pattern detection (§6 of the debate plan) is particularly important: when the AI proactively says "You keep overriding me on tech positions, and it's cost you $18K — should I adjust my threshold?", that is the system earning trust through demonstrated self-awareness.

## For Discussion

- What is the minimum viable version of this trust loop? Could v1 ship with debate + counterfactual tracking but defer the automated override pattern detection to v2?
- How long does the trust calibration loop take to produce meaningful data? If it requires 50+ decisions to calibrate, and the system makes ~2 decisions per week, that is 6 months before the system has enough track record. Is that acceptable?
- Could the trust calibration be accelerated with backtested counterfactuals? ("Here is what would have happened over the last 5 years if you had followed all my recommendations" — giving the user a simulated track record before the real one exists)
