from graph.state import CallState
from guardrails.pii_masker import mask_pii


def _build_summary(state: CallState) -> str:
    parts = []
    if state.get("patient_name"):
        parts.append(f"Patient: {state['patient_name']}")
    intents = [i.value for i in state["previous_intents"]]
    if intents:
        parts.append(f"Intents: {', '.join(intents)}")
    if state.get("requested_doctor"):
        parts.append(f"Requested doctor: {state['requested_doctor']}")
    if state.get("requested_date"):
        parts.append(f"Requested date: {state['requested_date']}")
    if state.get("booked_appointment_id"):
        parts.append(f"Appointment booked: #{state['booked_appointment_id']}")
    if state.get("guardrail_triggered"):
        parts.append(f"Escalation reason: {state['guardrail_triggered']}")
    else:
        parts.append("Escalation reason: patient requested")
    parts.append(f"Turns: {state['turn_count']}")
    return mask_pii(". ".join(parts))


def escalation_agent(state: CallState) -> CallState:
    state["escalated"] = True
    state["call_outcome"] = "escalated"
    state["call_summary"] = _build_summary(state)

    if state.get("guardrail_triggered") == "abuse":
        state["agent_response"] = (
            "I need to transfer you to our front desk team. Please hold."
        )
    else:
        state["agent_response"] = (
            "I understand. Let me connect you with our front desk team. "
            "They'll have a summary of our conversation so you won't need to repeat yourself. "
            "Please hold for a moment."
        )
    return state
