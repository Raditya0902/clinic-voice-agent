from db.appointments import get_patient_appointments
from db.scheduling import cancel_appointment
from agents.appointment_workflow import (
    clear_last_confirmed_appointment_if_matches,
    latest_confirmed_appointment,
    reset_active_booking_fields,
    reset_pending_existing_appointment_fields,
)
from graph.state import CallState


_YES_WORDS = {
    "yes",
    "yeah",
    "yep",
    "correct",
    "confirm",
    "confirmed",
    "please do",
    "go ahead",
    "cancel it",
    "cancel that",
    "cancel the appointment",
}

_NO_WORDS = {
    "no",
    "nope",
    "not",
    "don't",
    "dont",
    "do not",
    "never mind",
    "keep it",
    "keep that",
}


def _fmt(time_str: str) -> str:
    try:
        h, m = map(int, time_str.split(":"))
        period = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {period}"
    except Exception:
        return time_str


def _appointment_summary(appt: dict) -> str:
    return (
        f"{_fmt(appt['start_time'])} appointment with "
        f"{appt['doctor_name']} on {appt['date']}"
    )


def _is_affirmative(utterance: str) -> bool:
    text = utterance.lower()
    if any(word in text for word in _NO_WORDS):
        return False
    return any(word in text for word in _YES_WORDS)


def _is_negative(utterance: str) -> bool:
    text = utterance.lower()
    return any(word in text for word in _NO_WORDS)


def cancellation_agent(state: CallState) -> CallState:
    patient_id = state["patient_id"]
    if not patient_id:
        state["agent_response"] = (
            "I need to verify your identity before cancelling. "
            "Please call (480) 555-0100 for help."
        )
        return state

    pending_appt = state.get("existing_appointment_details")
    if (
        state.get("existing_appointment_id") is not None
        and pending_appt
        and state.get("call_outcome") != "cancelled"
    ):
        if _is_negative(state["current_utterance"]):
            reset_pending_existing_appointment_fields(state)
            state["agent_response"] = (
                "Okay, I will leave that appointment as is. "
                "Is there anything else I can help you with?"
            )
            return state

        if not _is_affirmative(state["current_utterance"]):
            state["agent_response"] = (
                f"Just to confirm, should I cancel your "
                f"{_appointment_summary(pending_appt)}?"
            )
            return state

        try:
            cancel_appointment(state["existing_appointment_id"])
        except Exception as exc:
            print(f"Cancellation error: {exc}")
            state["agent_response"] = (
                "I'm sorry, I had trouble cancelling your appointment. "
                "Please call (480) 555-0100 and our team will sort it out."
            )
            return state

        cancelled_id = state["existing_appointment_id"]
        clear_last_confirmed_appointment_if_matches(state, cancelled_id)
        reset_pending_existing_appointment_fields(state)
        state["call_outcome"] = "cancelled"
        state["agent_response"] = (
            f"Done! Your {_appointment_summary(pending_appt)} has been cancelled. "
            "Is there anything else I can help you with?"
        )
        return state

    reset_active_booking_fields(state)
    reset_pending_existing_appointment_fields(state)
    state["active_appointment_workflow"] = "cancel"
    if state.get("call_outcome") == "cancelled":
        state["call_outcome"] = None

    appt = latest_confirmed_appointment(state)
    if not appt:
        appointments = get_patient_appointments(patient_id)
        appt = appointments[0] if appointments else None

    if not appt:
        state["agent_response"] = (
            "I don't see any upcoming appointments on your account. "
            "If you think this is an error, please call (480) 555-0100."
        )
        return state

    state["existing_appointment_id"] = appt["id"]
    state["existing_appointment_details"] = appt
    state["agent_response"] = (
        f"I found your {_appointment_summary(appt)}. "
        "Should I cancel this appointment?"
    )
    return state
