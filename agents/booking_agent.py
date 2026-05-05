import json
from datetime import datetime, timezone

from db.doctors import find_doctor_by_name, get_all_doctors
from db.scheduling import confirm_booking, get_available_slots, lock_slot
from graph.llm import get_llm
from graph.state import CallState


# ── LLM extraction helpers ────────────────────────────────────────────────────

def _extract_doctor(utterance: str, doctor_list: str) -> str | None:
    prompt = (
        f"Available doctors:\n{doctor_list}\n\n"
        f'Patient said: "{utterance}"\n'
        "Which doctor are they asking for? Return JSON only:\n"
        '{"doctor_name": "Dr. Sarah Smith"} or {"doctor_name": null} if not mentioned.'
    )
    try:
        resp = get_llm().invoke([{"role": "system", "content": prompt}])
        data = json.loads(resp.content.strip())
        return data.get("doctor_name")
    except Exception:
        return None


def _extract_date(utterance: str) -> str | None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = (
        f"Today is {today}. Extract the appointment date from the patient's message.\n"
        "Convert relative dates (tomorrow, Friday, next week) to YYYY-MM-DD.\n"
        f'Patient said: "{utterance}"\n'
        'Return JSON only: {"date": "2026-05-10"} or {"date": null} if not mentioned.'
    )
    try:
        resp = get_llm().invoke([{"role": "system", "content": prompt}])
        data = json.loads(resp.content.strip())
        return data.get("date")
    except Exception:
        return None


def _extract_slot_index(utterance: str, slots: list[dict]) -> int | None:
    slot_list = "\n".join(f"{i}. {_fmt(s['start_time'])}" for i, s in enumerate(slots))
    prompt = (
        f"Available time slots:\n{slot_list}\n\n"
        f'Patient said: "{utterance}"\n'
        "Which slot are they choosing? Return JSON only:\n"
        '{"slot_index": 0} (0-based) or {"slot_index": null} if unclear.'
    )
    try:
        resp = get_llm().invoke([{"role": "system", "content": prompt}])
        data = json.loads(resp.content.strip())
        idx = data.get("slot_index")
        if idx is not None and 0 <= int(idx) < len(slots):
            return int(idx)
        return None
    except Exception:
        return None


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt(time_str: str) -> str:
    """'09:00' → '9:00 AM',  '14:30' → '2:30 PM'"""
    try:
        h, m = map(int, time_str.split(":"))
        period = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {period}"
    except Exception:
        return time_str


def _last_agent_message(state: CallState) -> str:
    for turn in reversed(state["conversation_history"]):
        if turn["role"] == "agent":
            return turn["text"]
    return ""


# ── Stage handlers ────────────────────────────────────────────────────────────

def _ask_for_doctor(state: CallState, greeting: str = "") -> CallState:
    doctors = get_all_doctors()
    names = ", ".join(d["name"] for d in doctors)
    prefix = f"{greeting} " if greeting else ""
    state["agent_response"] = (
        f"{prefix}Which doctor would you like to see? "
        f"We have: {names}."
    )
    return state


def _handle_doctor_stage(state: CallState) -> CallState:
    # Build greeting if verification just succeeded this turn
    first_name = (state["patient_name"] or "").split()[0] if state["patient_name"] else ""
    greeting = f"Great, {first_name}." if first_name else "Great."

    doctors = get_all_doctors()
    doctor_list = "\n".join(f"- {d['name']} ({d['specialty']})" for d in doctors)
    doctor_name = _extract_doctor(state["current_utterance"], doctor_list)

    if doctor_name:
        doctor = find_doctor_by_name(doctor_name)
        if doctor:
            state["requested_doctor"] = doctor["name"]
            state["requested_doctor_id"] = doctor["id"]
            state["agent_response"] = (
                f"I'll book you with {doctor['name']}. "
                "What date would you like for your appointment?"
            )
            return state

    return _ask_for_doctor(state, greeting)


def _handle_date_stage(state: CallState) -> CallState:
    date = _extract_date(state["current_utterance"])
    if date:
        state["requested_date"] = date
        return _fetch_and_present_slots(state)

    state["agent_response"] = (
        "What date would you like? "
        "You can say something like 'this Friday' or 'May 10th'."
    )
    return state


def _fetch_and_present_slots(state: CallState) -> CallState:
    doctor_id = state["requested_doctor_id"]
    date = state["requested_date"]

    if not doctor_id:
        doctor = find_doctor_by_name(state["requested_doctor"] or "")
        if not doctor:
            state["agent_response"] = (
                "I'm having trouble looking up that doctor. "
                "Please call (480) 555-0100 for help."
            )
            return state
        doctor_id = doctor["id"]
        state["requested_doctor_id"] = doctor_id

    slots = get_available_slots(doctor_id, date)

    if not slots:
        state["requested_date"] = None
        state["available_slots"] = []
        state["agent_response"] = (
            f"There are no available slots with {state['requested_doctor']} on {date}. "
            "Could you choose a different date?"
        )
        return state

    displayed = slots[:4]
    state["available_slots"] = displayed
    times = ", ".join(_fmt(s["start_time"]) for s in displayed)
    state["agent_response"] = (
        f"I have these times available on {date}: {times}. "
        "Which time works for you?"
    )
    return state


def _handle_slot_selection(state: CallState) -> CallState:
    slots = state["available_slots"]
    idx = _extract_slot_index(state["current_utterance"], slots)

    if idx is None:
        times = ", ".join(_fmt(s["start_time"]) for s in slots)
        state["agent_response"] = (
            f"I didn't catch that. Available times are: {times}. "
            "Which would you like?"
        )
        return state

    chosen = slots[idx]
    locked = lock_slot(chosen["slot_id"], state["call_sid"])

    if not locked:
        remaining = [s for s in slots if s["slot_id"] != chosen["slot_id"]]
        state["available_slots"] = remaining
        if remaining:
            times = ", ".join(_fmt(s["start_time"]) for s in remaining)
            state["agent_response"] = (
                f"Sorry, that slot was just taken. I still have: {times}. "
                "Which would you like?"
            )
        else:
            state["requested_date"] = None
            state["available_slots"] = []
            state["agent_response"] = (
                "Sorry, all slots for that date are now taken. "
                "Would you like to try a different date?"
            )
        return state

    state["locked_slot_id"] = chosen["slot_id"]
    state["requested_time"] = chosen["start_time"]
    state["agent_response"] = (
        f"I've reserved the {_fmt(chosen['start_time'])} slot. "
        "What is the reason for your visit today?"
    )
    return state


def _handle_reason_stage(state: CallState) -> CallState:
    last = _last_agent_message(state)
    if "reason for your visit" in last.lower():
        reason = state["current_utterance"].strip()
        if reason:
            state["reason_for_visit"] = reason
            return _confirm_booking(state)

    state["agent_response"] = "What is the reason for your visit today?"
    return state


def _confirm_booking(state: CallState) -> CallState:
    try:
        appt_id = confirm_booking(
            slot_id=state["locked_slot_id"],
            call_sid=state["call_sid"],
            patient_id=state["patient_id"],
            reason=state["reason_for_visit"],
        )
        state["booked_appointment_id"] = appt_id
        state["call_outcome"] = "booked"
        state["agent_response"] = (
            f"You're all set! Your appointment with {state['requested_doctor']} "
            f"is confirmed for {state['requested_date']} at "
            f"{_fmt(state['requested_time'])}. "
            "Is there anything else I can help you with?"
        )
    except Exception as exc:
        print(f"Booking confirmation error: {exc}")
        state["agent_response"] = (
            "I'm sorry, I had trouble confirming your booking. "
            "Please call (480) 555-0100 and our team will help you."
        )
    return state


# ── Main entry point ──────────────────────────────────────────────────────────

def booking_agent(state: CallState) -> CallState:
    # Already booked — just confirm again (shouldn't normally re-enter)
    if state["booked_appointment_id"] is not None:
        state["agent_response"] = (
            f"Your appointment with {state['requested_doctor']} on "
            f"{state['requested_date']} at {_fmt(state['requested_time'])} "
            "is already confirmed. Is there anything else I can help you with?"
        )
        return state

    if not state["requested_doctor"]:
        return _handle_doctor_stage(state)

    if not state["requested_date"]:
        return _handle_date_stage(state)

    # Slots not yet fetched (date just set but slots are empty)
    if not state["available_slots"] and state["locked_slot_id"] is None:
        return _fetch_and_present_slots(state)

    if state["locked_slot_id"] is None:
        return _handle_slot_selection(state)

    if not state["reason_for_visit"]:
        return _handle_reason_stage(state)

    return _confirm_booking(state)
