from __future__ import annotations

from typing import Literal

from db.scheduling import release_slot
from graph.state import CallState

AppointmentWorkflow = Literal["booking", "reschedule", "cancel"]


def release_unconfirmed_slot(state: CallState) -> None:
    slot_id = state.get("locked_slot_id")
    if not slot_id or state.get("booked_appointment_id") is not None:
        return

    try:
        release_slot(slot_id, state["call_sid"])
    except Exception as exc:
        print(f"slot release error: {exc}")


def reset_active_booking_fields(state: CallState, *, release_lock: bool = True) -> None:
    if release_lock:
        release_unconfirmed_slot(state)

    state["requested_doctor"] = None
    state["requested_doctor_id"] = None
    state["requested_date"] = None
    state["requested_time"] = None
    state["reason_for_visit"] = None
    state["available_slots"] = []
    state["locked_slot_id"] = None
    state["booked_appointment_id"] = None


def reset_pending_existing_appointment_fields(state: CallState) -> None:
    state["existing_appointment_id"] = None
    state["existing_appointment_details"] = None


def start_appointment_workflow(state: CallState, workflow: AppointmentWorkflow) -> None:
    reset_active_booking_fields(state)
    reset_pending_existing_appointment_fields(state)
    state["active_appointment_workflow"] = workflow
    if workflow != "cancel" or state.get("call_outcome") == "cancelled":
        state["call_outcome"] = None


def appointment_details_from_state(
    state: CallState,
    appointment_id: int,
) -> dict:
    return {
        "id": appointment_id,
        "doctor_id": state.get("requested_doctor_id"),
        "doctor_name": state.get("requested_doctor"),
        "date": state.get("requested_date"),
        "start_time": state.get("requested_time"),
        "reason": state.get("reason_for_visit"),
    }


def set_last_confirmed_appointment(state: CallState, details: dict) -> None:
    appointment_id = details.get("id")
    state["last_confirmed_appointment_id"] = appointment_id
    state["last_confirmed_appointment_details"] = {
        "id": appointment_id,
        "doctor_id": details.get("doctor_id"),
        "doctor_name": details.get("doctor_name"),
        "date": details.get("date"),
        "start_time": details.get("start_time"),
        "reason": details.get("reason"),
    }


def clear_last_confirmed_appointment_if_matches(
    state: CallState,
    appointment_id: int | None,
) -> None:
    if appointment_id is None:
        return
    if state.get("last_confirmed_appointment_id") == appointment_id:
        state["last_confirmed_appointment_id"] = None
        state["last_confirmed_appointment_details"] = None


def latest_confirmed_appointment(state: CallState) -> dict | None:
    details = state.get("last_confirmed_appointment_details")
    if not details:
        return None
    if details.get("id") is None:
        return None
    return details
