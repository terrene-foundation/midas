"""Top-of-fold card — decide-in-10s display per T-00-08.

Renders a compact decision card with the essential information needed
to approve, reject, or open debate in under 10 seconds.
"""


class TopOfFoldCard:
    """Decide-in-10s card.

    Renders the minimum information needed for a decision:
    - action_line: one sentence describing the proposal
    - counter_evidence: one bullet against
    - what_would_change_mind: one sentence
    - buttons: approve, reject, debate
    """

    @staticmethod
    def render_card(decision: dict) -> dict:
        """Render top-of-fold card.

        Parameters
        ----------
        decision:
            Dict with decision metadata including recommendation,
            counter_evidence, what_would_change_mind, confidence.

        Returns
        -------
        dict
            Card with keys: action_line, counter_evidence,
            what_would_change_mind, buttons, confidence.
        """
        # Extract or derive the action line
        recommendation = decision.get("recommendation", "")
        instruments = decision.get("instruments", [])
        action = decision.get("action", "")

        if recommendation:
            action_line = recommendation
        elif action and instruments:
            ticker_str = (
                ", ".join(instruments) if isinstance(instruments, list) else str(instruments)
            )
            action_line = f"{action.replace('_', ' ').title()}: {ticker_str}"
        else:
            action_line = "Review pending decision."

        # Extract counter-evidence
        counter_evidence = decision.get("counter_evidence", "No counter-evidence available.")

        # Extract what-would-change-mind
        what_would_change_mind = decision.get(
            "what_would_change_mind", "No reversal criteria specified."
        )

        confidence = decision.get("confidence", 0.0)

        return {
            "action_line": action_line,
            "counter_evidence": counter_evidence,
            "what_would_change_mind": what_would_change_mind,
            "confidence": confidence,
            "buttons": [
                {"label": "Approve", "action": "approve"},
                {"label": "Reject", "action": "reject"},
                {"label": "Debate", "action": "debate"},
            ],
        }
