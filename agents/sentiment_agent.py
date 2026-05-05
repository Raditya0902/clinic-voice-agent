from graph.state import CallIntent, CallState
from guardrails.abuse_detector import is_abusive

_FRUSTRATION_WORDS = {
    "frustrated", "frustrating", "annoyed", "annoying", "ridiculous",
    "unacceptable", "absurd", "terrible", "awful", "horrible",
    "waste", "useless", "not working", "doesn't work",
    "wrong", "mistake", "problem",
}

_ESCALATION_PHRASES = {
    "speak to a human", "speak to someone", "real person",
    "talk to a person", "talk to someone", "human please",
    "manager", "supervisor", "representative",
    "i give up", "forget it",
}

_AUTO_ESCALATE_THRESHOLD = 0.75


def sentiment_agent(state: CallState) -> CallState:
    utterance = state["current_utterance"].lower()

    if is_abusive(utterance):
        state["guardrail_triggered"] = "abuse"
        state["current_intent"] = CallIntent.ESCALATE
        return state

    explicit = any(phrase in utterance for phrase in _ESCALATION_PHRASES)
    hits = sum(1 for word in _FRUSTRATION_WORDS if word in utterance)
    increment = (0.4 if explicit else 0.0) + hits * 0.15

    new_score = min(1.0, state["frustration_score"] + increment)
    state["frustration_score"] = new_score

    if new_score >= _AUTO_ESCALATE_THRESHOLD:
        state["guardrail_triggered"] = "frustration"
        state["current_intent"] = CallIntent.ESCALATE

    return state
