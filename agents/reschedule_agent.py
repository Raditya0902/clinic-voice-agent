from db.appointments import get_patient_appointments
from db.scheduling import cancel_appointment
from agents.appointment_workflow import (
    appointment_details_from_state,
    latest_confirmed_appointment,
    reset_active_booking_fields,
    reset_pending_existing_appointment_fields,
    set_last_confirmed_appointment,
)
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
    # Stage 1: find the old appointment, but keep it until the new slot is confirmed.
    reschedule_in_progress = (
        state["existing_appointment_id"] is not None
        and state.get("existing_appointment_details") is not None
        and state.get("call_outcome") != "cancelled"
    )

    if not reschedule_in_progress:
        reset_active_booking_fields(state)
        reset_pending_existing_appointment_fields(state)
        state["active_appointment_workflow"] = "reschedule"
        state["call_outcome"] = None

        appt = latest_confirmed_appointment(state)
        if not appt:
            appointments = get_patient_appointments(state["patient_id"])
            appt = appointments[0] if appointments else None

        if not appt:
            state["agent_response"] = (
                "I don't see any upcoming appointments on your account. "
                "Would you like to book a new one instead?"
            )
            return state

        state["existing_appointment_id"] = appt["id"]
        state["existing_appointment_details"] = appt
        # Pre-fill doctor from old appointment so booking skips that step
        state["requested_doctor"] = appt["doctor_name"]
        state["requested_doctor_id"] = appt["doctor_id"]
        state["agent_response"] = (
            f"I found your {_fmt(appt['start_time'])} appointment with "
            f"{appt['doctor_name']} on {appt['date']}. I'll keep that appointment "
            "in place while we find a new time. "
            "What date would you like for the new appointment?"
        )
        return state

    # Stage 2+: delegate to the booking flow
    # existing_appointment_id is set, doctor is pre-filled — booking agent handles the rest
    from agents.booking_agent import booking_agent
    state = booking_agent(state)

    if state.get("booked_appointment_id") and state.get("call_outcome") == "booked":
        old = state.get("existing_appointment_details") or {}
        old_id = state.get("existing_appointment_id")
        try:
            cancel_appointment(old_id)
        except Exception as exc:
            print(f"Reschedule cancel error: {exc}")
            state["escalated"] = True
            state["call_outcome"] = "escalated"
            state["agent_response"] = (
                "Your new appointment is booked, but I had trouble cancelling "
                "your previous appointment. Let me connect you with our front desk "
                "so they can clean that up."
            )
            return state

        set_last_confirmed_appointment(
            state,
            appointment_details_from_state(state, state["booked_appointment_id"]),
        )
        reset_pending_existing_appointment_fields(state)
        state["call_outcome"] = "rescheduled"
        state["agent_response"] = (
            f"You're all set. Your previous {_fmt(old.get('start_time', ''))} "
            f"appointment with {old.get('doctor_name', 'the doctor')} on "
            f"{old.get('date', 'the old date')} has been cancelled, and your new "
            f"appointment with {state['requested_doctor']} is confirmed for "
            f"{state['requested_date']} at {_fmt(state['requested_time'])}. "
            "Is there anything else I can help you with?"
        )

    return state
