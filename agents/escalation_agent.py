import os

import httpx

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
    return mask_pii(". ".join(parts), names=[state["patient_name"]] if state.get("patient_name") else None)


def _send_slack_notification(state: CallState) -> None:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return

    summary = mask_pii(
        state.get("call_summary") or "Voice agent escalation.",
        names=[state["patient_name"]] if state.get("patient_name") else None,
    )
    payload = {
        "text": (
            "*Sunrise Health Clinic voice escalation*\n"
            f"{summary}\n"
            f"Reason: {state.get('guardrail_triggered') or 'patient requested'}"
        )
    }
    try:
        httpx.post(webhook_url, json=payload, timeout=2.0)
    except Exception as exc:
        print(f"[slack] notification failed: {type(exc).__name__}")


def escalation_agent(state: CallState) -> CallState:
    state["escalated"] = True
    state["call_outcome"] = "escalated"
    state["call_summary"] = _build_summary(state)
    _send_slack_notification(state)

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
