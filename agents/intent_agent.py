import json
import re

from agents.appointment_workflow import start_appointment_workflow
from graph.llm import get_llm
from graph.state import CallIntent, CallState
from guardrails.scope_detector import is_in_scope

_FAREWELL_PHRASES = {
    "bye", "goodbye", "good bye", "that's all", "that is all",
    "thanks bye", "thank you bye", "have a good day", "have a great day",
    "take care", "see you", "see ya", "no that's it", "no that is it",
}

_LOW_CONTENT_WORDS = {
    "uh", "um", "hmm", "hm", "i", "do", "dont", "don't", "know",
    "not", "sure", "maybe", "hello", "hi", "hey",
}

_CONFIRMATION_WORDS = {
    "yes", "yeah", "yep", "confirm", "correct", "go ahead", "please do",
    "cancel it", "cancel that", "no", "nope", "don't", "dont", "do not",
    "never mind", "keep it",
}

_ANYTHING_ELSE_NEGATIONS = {
    "no",
    "nope",
    "no thanks",
    "no thank you",
    "nothing else",
    "that's all",
    "that is all",
}

_TRANSACTIONAL_PROMPT_MARKERS = {
    "which doctor",
    "what date",
    "different date",
    "which time",
    "which would you like",
    "which time works",
    "available times",
    "reason for your visit",
}

_DONE_OUTCOMES = {"booked", "cancelled", "rescheduled", "escalated"}
_APPOINTMENT_INTENTS = {CallIntent.BOOKING, CallIntent.RESCHEDULE}
_WORKFLOW_START_INTENTS = {
    CallIntent.BOOKING,
    CallIntent.RESCHEDULE,
    CallIntent.CANCEL,
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


def _substantive_out_of_scope(utterance: str) -> bool:
    if is_in_scope(utterance):
        return False
    words = re.findall(r"[a-z']+", utterance.lower())
    meaningful = [w for w in words if w not in _LOW_CONTENT_WORDS]
    return len(meaningful) >= 2


def _is_pending_cancellation_confirmation(state: CallState, utterance_lower: str) -> bool:
    if not (
        state.get("existing_appointment_id") is not None
        and state.get("existing_appointment_details") is not None
        and state.get("call_outcome") != "cancelled"
    ):
        return False

    last_agent = ""
    for turn in reversed(state["conversation_history"]):
        if turn["role"] == "agent":
            last_agent = turn["text"].lower()
            break

    return "should i cancel" in last_agent and any(
        word in utterance_lower for word in _CONFIRMATION_WORDS
    )


def _last_agent_message(state: CallState) -> str:
    for turn in reversed(state["conversation_history"]):
        if turn["role"] == "agent":
            return turn["text"].lower()
    return ""


def _is_done_after_anything_else(state: CallState, utterance_lower: str) -> bool:
    last_agent = _last_agent_message(state)
    return "anything else" in last_agent and any(
        phrase in utterance_lower for phrase in _ANYTHING_ELSE_NEGATIONS
    )


def _last_appointment_intent(state: CallState) -> CallIntent | None:
    workflow = state.get("active_appointment_workflow")
    if workflow == "booking":
        return CallIntent.BOOKING
    if workflow == "reschedule":
        return CallIntent.RESCHEDULE

    current = state.get("current_intent")
    if current in _APPOINTMENT_INTENTS:
        return current

    for intent in reversed(state.get("previous_intents", [])):
        if intent in _APPOINTMENT_INTENTS:
            return intent
    return None


def _active_workflow_intent(state: CallState) -> CallIntent | None:
    last_agent = _last_agent_message(state)
    if not any(marker in last_agent for marker in _TRANSACTIONAL_PROMPT_MARKERS):
        return None

    outcome = state.get("call_outcome")
    if (
        state.get("existing_appointment_id") is not None
        and state.get("existing_appointment_details") is not None
        and outcome not in {"cancelled", "rescheduled", "escalated"}
    ):
        return CallIntent.RESCHEDULE

    if (
        state.get("patient_verified")
        and "which doctor" in last_agent
        and state.get("requested_doctor") is None
        and outcome not in _DONE_OUTCOMES
    ):
        return _last_appointment_intent(state)

    booking_fields_present = any(
        (
            state.get("requested_doctor"),
            state.get("requested_date"),
            state.get("available_slots"),
            state.get("locked_slot_id"),
        )
    )
    if (
        booking_fields_present
        and state.get("booked_appointment_id") is None
        and outcome not in _DONE_OUTCOMES
    ):
        return CallIntent.BOOKING

    return None


def intent_agent(state: CallState) -> CallState:
    # Safety guardrails already fired — don't override forced escalation.
    if state.get("guardrail_triggered") in ("abuse", "frustration"):
        return state
    if state.get("guardrail_triggered") == "out_of_scope":
        state["guardrail_triggered"] = None

    # Farewell detection — no LLM needed
    utterance_lower = state["current_utterance"].lower()
    if any(phrase in utterance_lower for phrase in _FAREWELL_PHRASES):
        state["current_intent"] = CallIntent.FAREWELL
        state["previous_intents"] = state["previous_intents"] + [CallIntent.FAREWELL]
        return state

    if _is_done_after_anything_else(state, utterance_lower):
        state["current_intent"] = CallIntent.FAREWELL
        state["intent_confidence"] = 1.0
        state["previous_intents"] = state["previous_intents"] + [CallIntent.FAREWELL]
        return state

    if _is_pending_cancellation_confirmation(state, utterance_lower):
        state["current_intent"] = CallIntent.CANCEL
        state["intent_confidence"] = 1.0
        state["previous_intents"] = state["previous_intents"] + [CallIntent.CANCEL]
        return state

    active_intent = _active_workflow_intent(state)
    if active_intent:
        state["current_intent"] = active_intent
        state["intent_confidence"] = 1.0
        state["previous_intents"] = state["previous_intents"] + [active_intent]
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
    if state["current_intent"] in _WORKFLOW_START_INTENTS:
        start_appointment_workflow(state, state["current_intent"].value)
    state["previous_intents"] = state["previous_intents"] + [state["current_intent"]]

    if state["current_intent"] == CallIntent.UNKNOWN:
        state["current_intent"] = CallIntent.UNKNOWN
        if _substantive_out_of_scope(utterance):
            state["guardrail_triggered"] = "out_of_scope"
            state["agent_response"] = (
                "I can help with appointments or questions about the clinic. "
                "Would you like to book, cancel, reschedule, or ask about clinic information?"
            )
        else:
            state["agent_response"] = (
                "I'm sorry, I didn't quite catch that. "
                "Could you tell me what you need help with — "
                "booking, cancelling, rescheduling, or a question about the clinic?"
            )

    return state
