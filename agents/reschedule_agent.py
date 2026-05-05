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


def reschedule_agent(state: CallState) -> CallState:
    # Stage 1: find and cancel the old appointment
    if state["existing_appointment_id"] is None:
        appointments = get_patient_appointments(state["patient_id"])

        if not appointments:
            state["agent_response"] = (
                "I don't see any upcoming appointments on your account. "
                "Would you like to book a new one instead?"
            )
            return state

        appt = appointments[0]
        try:
            cancel_appointment(appt["id"])
        except Exception as exc:
            print(f"Reschedule cancel error: {exc}")
            state["agent_response"] = (
                "I'm sorry, I had trouble modifying your appointment. "
                "Please call (480) 555-0100 for help."
            )
            return state

        state["existing_appointment_id"] = appt["id"]
        state["existing_appointment_details"] = appt
        # Pre-fill doctor from old appointment so booking skips that step
        state["requested_doctor"] = appt["doctor_name"]
        state["requested_doctor_id"] = appt["doctor_id"]
        state["agent_response"] = (
            f"I've cancelled your {_fmt(appt['start_time'])} appointment with "
            f"{appt['doctor_name']} on {appt['date']}. "
            "What date would you like for the new appointment?"
        )
        return state

    # Stage 2+: delegate to the booking flow
    # existing_appointment_id is set, doctor is pre-filled — booking agent handles the rest
    from agents.booking_agent import booking_agent
    return booking_agent(state)
