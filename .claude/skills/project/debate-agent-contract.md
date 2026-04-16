# Debate Agent Contract

The Debate agent is load-bearing infrastructure, not a chatbot add-on. It MUST be able to mutate pending decisions, not just narrate about them.

**Spec authority:** `specs/07-evidence-first-decision.md`, FP-8 (evidence-first co-decision)

---

## Core Principles

1. **Debate must write, not just read** — the agent needs tools that modify pending decision weights, propose alternative allocations, re-run the optimizer under user constraints, and generate counterfactuals on demand
2. **"What would change my mind"** — every recommendation carries an appendix specifying the evidence or threshold that would flip the call
3. **Confidence is a distribution** — briefs show evidence with uncertainty; decisions are where user and Midas meet
4. **Evidence provenance is unbroken** — every number traces to a fabric row, model version, or tool call
5. **Parse failures must return honest signals** — never fabricate steel_man or red_team text

---

## Required Tools (10 MCP tools)

| Tool                             | Capability                                      |
| -------------------------------- | ----------------------------------------------- |
| `query_fabric`                   | Read any fabric table (prices, positions, etc.) |
| `query_head`                     | Query model head predictions from z_t           |
| `query_calibration`              | Check model calibration data                    |
| `retrieve_analogue`              | Find similar historical situations              |
| `propose_alternative_allocation` | Compute adjusted weight allocation              |
| `recompute_with_constraint`      | Re-run optimizer under modified constraints     |
| `backtest_scenario`              | Run quick backtest on proposed weights          |
| `update_decision`                | Write updates to a pending decision             |
| `generate_counterfactual`        | Show opposite-action outcome                    |
| `surface_override_pattern`       | Analyze user's historical override behavior     |

Tools 5–8 are the **write-capable** tools. Without them, the debate is read-only narration.

---

## Non-Sycophancy Rules (from specs/10-moments-of-truth.md §4)

- Disagree when evidence warrants — always
- Present counter-evidence with specific data
- Decline to confabulate justifications for unsupported actions
- Honestly surface calibration weakness
- Concede when the user makes a stronger case — stubbornness is also wrong

---

## Error Handling

When the LLM response fails to parse as valid JSON:

```python
# DO — honest failure signal
result = {
    "recommendation": "parse_failed",
    "steel_man": "",
    "red_team": "",
    "concession_count": 0,
    "final_confidence": 0.0,
    "parse_error": True,
    "raw_content_preview": content[:100],
}

# DO NOT — fabricated debate text
result = {
    "recommendation": "hold",
    "steel_man": "The market appears stable...",  # made up
    "red_team": "However, risks remain...",       # made up
}
```

---

## Implementation Location

- Agent: `src/midas/agents/debate.py` — `DebateAgent` class
- Tools: `src/midas/agents/tools.py` — `DebateTools` class (10 tools)
- API routes: `src/midas/api/routes.py` — `DebateRouter`
- Tests: `tests/test_debate.py`
