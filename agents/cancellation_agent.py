from db.appointments import get_patient_appointments
from db.scheduling import cancel_appointment
from graph.state import CallState


def _fmt(time_str: str) -> str:
    try:
        h, m = map(int, time_str.split(":"))
        period = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {period}"
    except Exception:
        return time_str


def cancellation_agent(state: CallState) -> CallState:
    patient_id = state["patient_id"]
    if not patient_id:
        state["agent_response"] = (
            "I need to verify your identity before cancelling. "
            "Please call (480) 555-0100 for help."
        )
        return state

    appointments = get_patient_appointments(patient_id)

    if not appointments:
        state["agent_response"] = (
            "I don't see any upcoming appointments on your account. "
            "If you think this is an error, please call (480) 555-0100."
        )
        return state

    # Cancel the earliest upcoming appointment
    appt = appointments[0]
    try:
        cancel_appointment(appt["id"])
    except Exception as exc:
        print(f"Cancellation error: {exc}")
        state["agent_response"] = (
            "I'm sorry, I had trouble cancelling your appointment. "
            "Please call (480) 555-0100 and our team will sort it out."
        )
        return state

    state["existing_appointment_id"] = appt["id"]
    state["existing_appointment_details"] = appt
    state["call_outcome"] = "cancelled"
    state["agent_response"] = (
        f"Done! Your {_fmt(appt['start_time'])} appointment with {appt['doctor_name']} "
        f"on {appt['date']} has been cancelled. "
        "Is there anything else I can help you with?"
    )
    return state
