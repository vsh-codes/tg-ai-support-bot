"""
Escalation logic.

The bot escalates to a human in three situations:

1. **Explicit request** — the user types a phrase that signals they want
   a human ("agent", "human", "talk to person", etc., in any language we
   detect).

2. **Low-confidence response** — the model's own response contains
   uncertainty markers ("I don't know", "I'm not sure", "I don't have
   information about"). These are reliable signals because the system
   prompt instructs the model to admit gaps rather than guess.

3. **Repeated dead-ends** — three consecutive turns where the bot
   couldn't find relevant context in the knowledge base. Tracked by the
   storage layer.

The detection is deliberately rule-based — fast, deterministic, and easy
to audit. A learned classifier would add latency and opacity for marginal
gain at this scale.
"""

from dataclasses import dataclass


# Words/phrases that indicate the user explicitly wants a human.
# Lowercase, will be matched as substrings against the lowercase user message.
_HUMAN_REQUEST_PATTERNS = (
    "human",
    "agent",
    "person",
    "real support",
    "speak to someone",
    "talk to someone",
    "talk to a person",
    "operator",
    "representative",
    # Russian
    "человек",
    "оператор",
    "поддержк",
    "живой",
    # Ukrainian
    "людин",
    "підтримк",
    "оператор",
    # Spanish
    "humano",
    "persona",
    "operador",
)

# Phrases in model responses that signal it didn't find the answer.
_UNCERTAINTY_PATTERNS = (
    "i don't know",
    "i don't have information",
    "i'm not sure",
    "i'm unable to",
    "i cannot find",
    "i could not find",
    "no information about",
    "not in my knowledge",
    "outside my knowledge",
    "i don't have specific information",
)

DEAD_END_THRESHOLD = 3


@dataclass(frozen=True)
class EscalationDecision:
    """Outcome of an escalation check."""

    should_escalate: bool
    reason: str = ""


def check_user_request(message_text: str) -> EscalationDecision:
    """True if the user's own message asks for a human."""
    lowered = message_text.lower()
    for pattern in _HUMAN_REQUEST_PATTERNS:
        if pattern in lowered:
            return EscalationDecision(
                should_escalate=True,
                reason=f"User explicitly requested human ('{pattern}')",
            )
    return EscalationDecision(should_escalate=False)


def check_response_uncertainty(response_text: str) -> EscalationDecision:
    """True if the model's response signals it couldn't answer."""
    lowered = response_text.lower()
    for pattern in _UNCERTAINTY_PATTERNS:
        if pattern in lowered:
            return EscalationDecision(
                should_escalate=True,
                reason=f"Low-confidence response ('{pattern}')",
            )
    return EscalationDecision(should_escalate=False)


def check_dead_end_streak(consecutive_no_context_turns: int) -> EscalationDecision:
    """True if we've had too many turns in a row without finding context."""
    if consecutive_no_context_turns >= DEAD_END_THRESHOLD:
        return EscalationDecision(
            should_escalate=True,
            reason=(
                f"{consecutive_no_context_turns} consecutive turns with no "
                "relevant context found in the knowledge base"
            ),
        )
    return EscalationDecision(should_escalate=False)
