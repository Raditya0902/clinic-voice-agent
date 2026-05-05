import json

from graph.llm import get_llm
from graph.state import CallIntent, CallState

_FAREWELL_PHRASES = {
    "bye", "goodbye", "good bye", "that's all", "that is all",
    "thanks bye", "thank you bye", "have a good day", "have a great day",
    "take care", "see you", "see ya", "no that's it", "no that is it",
}


_SYSTEM_PROMPT = """\
You are an intent classifier for a healthcare clinic phone system.
Given the patient's utterance and recent conversation, classify the intent.

Possible intents:
- booking: Patient wants to schedule a new appointment
- reschedule: Patient wants to change an existing appointment
- cancel: Patient wants to cancel an existing appointment
- faq: Patient is asking a general question about the clinic (hours, insurance, location, services)
- escalate: Patient explicitly asks for a human, or is clearly frustrated
- unknown: Cannot determine intent

Respond with JSON only — no prose, no markdown:
{"intent": "booking", "confidence": 0.95}"""


def intent_agent(state: CallState) -> CallState:
    # Guardrail already fired (abuse/frustration) — don't override
    if state.get("guardrail_triggered"):
        return state

    # Farewell detection — no LLM needed
    utterance_lower = state["current_utterance"].lower()
    if any(phrase in utterance_lower for phrase in _FAREWELL_PHRASES):
        state["current_intent"] = CallIntent.FAREWELL
        state["previous_intents"] = state["previous_intents"] + [CallIntent.FAREWELL]
        return state

    history = state["conversation_history"][-6:]  # last 3 turns
    utterance = state["current_utterance"]

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for turn in history:
        role = "user" if turn["role"] == "patient" else "assistant"
        messages.append({"role": role, "content": turn["text"]})
    messages.append({"role": "user", "content": utterance})

    try:
        response = get_llm().invoke(messages)
        raw = response.content.strip()
        print(f"[intent] raw LLM response: {raw!r}")
        result = json.loads(raw)
        intent_str = result.get("intent", "unknown")
        confidence = float(result.get("confidence", 0.0))
    except Exception as exc:
        print(f"[intent] ERROR — Groq call failed: {exc}")
        intent_str = "unknown"
        confidence = 0.0

    try:
        state["current_intent"] = CallIntent(intent_str)
    except ValueError:
        state["current_intent"] = CallIntent.UNKNOWN

    state["intent_confidence"] = confidence
    state["previous_intents"] = state["previous_intents"] + [state["current_intent"]]

    if confidence < 0.5:
        state["current_intent"] = CallIntent.UNKNOWN
        state["agent_response"] = (
            "I'm sorry, I didn't quite catch that. "
            "Could you tell me what you need help with — "
            "booking, cancelling, rescheduling, or a question about the clinic?"
        )

    return state
