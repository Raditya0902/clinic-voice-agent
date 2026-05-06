import json
import re
from datetime import datetime, timezone

from db.doctors import find_doctor_by_name, get_all_doctors
from db.scheduling import confirm_booking, get_available_slots, lock_slot
from agents.appointment_workflow import (
    appointment_details_from_state,
    set_last_confirmed_appointment,
)
from graph.llm import get_llm
from graph.state import CallState


# ── LLM extraction helpers ────────────────────────────────────────────────────

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_WORD_TIME_RE = re.compile(
    r"\b(?P<word>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b"
    r"(?:\s+(?P<marker>oclock))?"
    r"(?:\s*(?P<period>am|pm))?\b"
)
_NUMERIC_TIME_RE = re.compile(
    r"\b(?P<hour>2[0-3]|1[0-9]|0?[1-9])"
    r"(?::(?P<minute>[0-5]\d))?"
    r"(?:\s+(?P<marker>oclock))?"
    r"(?:\s*(?P<period>am|pm))?\b"
)
_DATE_HINT_RE = re.compile(
    r"\b("
    r"today|tomorrow|tonight|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun|"
    r"january|february|march|april|may|june|july|august|"
    r"september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|"
    r"next|this|"
    r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}"
    r")\b"
)
_DOCTOR_TITLE_TOKENS = {"dr", "doctor"}
_ORDINAL_WORDS = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
    "fourth": 3,
    "4th": 3,
}
_CARDINAL_OPTION_WORDS = {
    "one": 0,
    "two": 1,
    "three": 2,
    "four": 3,
}


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


def _name_tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _DOCTOR_TITLE_TOKENS
    ]


def _option_index_from_utterance(utterance: str, option_count: int) -> int | None:
    tokens = _name_tokens(utterance)
    if not tokens:
        return None

    token_set = set(tokens)
    if "last" in token_set and option_count:
        return option_count - 1
    if "earliest" in token_set:
        return 0 if option_count else None
    if "latest" in token_set:
        return option_count - 1 if option_count else None

    matches = {
        idx
        for word, idx in _ORDINAL_WORDS.items()
        if word in token_set and idx < option_count
    }

    for i, token in enumerate(tokens[:-1]):
        if token not in {"option", "number", "choice"}:
            continue
        idx = _CARDINAL_OPTION_WORDS.get(tokens[i + 1])
        if idx is not None and idx < option_count:
            matches.add(idx)

    if len(matches) == 1:
        return next(iter(matches))
    return None


def _token_phrase_present(phrase_tokens: list[str], utterance_tokens: list[str]) -> bool:
    if not phrase_tokens or len(phrase_tokens) > len(utterance_tokens):
        return False

    width = len(phrase_tokens)
    return any(
        utterance_tokens[i:i + width] == phrase_tokens
        for i in range(len(utterance_tokens) - width + 1)
    )


def _unique_token_counts(doctors: list[dict], token_index: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for doctor in doctors:
        tokens = _name_tokens(doctor["name"])
        if not tokens:
            continue
        if token_index >= 0 and len(tokens) <= token_index:
            continue
        token = tokens[token_index]
        counts[token] = counts.get(token, 0) + 1
    return counts


def _match_doctor_deterministically(utterance: str, doctors: list[dict]) -> dict | None:
    option_idx = _option_index_from_utterance(utterance, len(doctors))
    if option_idx is not None:
        return doctors[option_idx]

    utterance_tokens = _name_tokens(utterance)
    if not utterance_tokens:
        return None

    last_name_counts = _unique_token_counts(doctors, -1)
    first_name_counts = _unique_token_counts(doctors, 0)

    exact_matches = []
    first_last_matches = []
    last_name_matches = []
    first_name_matches = []

    for doctor in doctors:
        doctor_tokens = _name_tokens(doctor["name"])
        if not doctor_tokens:
            continue

        first = doctor_tokens[0]
        last = doctor_tokens[-1]
        token_set = set(utterance_tokens)

        if _token_phrase_present(doctor_tokens, utterance_tokens):
            exact_matches.append(doctor)
        elif first in token_set and last in token_set:
            first_last_matches.append(doctor)
        elif last in token_set and last_name_counts.get(last) == 1:
            last_name_matches.append(doctor)
        elif first in token_set and first_name_counts.get(first) == 1:
            first_name_matches.append(doctor)

    for matches in (exact_matches, first_last_matches, last_name_matches, first_name_matches):
        if len(matches) == 1:
            return matches[0]

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


def _utterance_may_include_date(utterance: str) -> bool:
    return bool(_DATE_HINT_RE.search(utterance.lower()))


def _normalize_time_utterance(utterance: str) -> str:
    text = utterance.lower().replace("’", "'")
    text = text.replace("a.m.", "am").replace("p.m.", "pm")
    text = re.sub(r"\ba\s*\.?\s*m\b", "am", text)
    text = re.sub(r"\bp\s*\.?\s*m\b", "pm", text)
    text = re.sub(r"\bo\s*'?\s*clock\b", "oclock", text)
    return text


def _parse_slot_start(start_time: str) -> tuple[int, int] | None:
    try:
        hour, minute = map(int, start_time.split(":")[:2])
    except Exception:
        return None
    return hour, minute


def _candidate_matches_slot(
    hour: int,
    minute: int,
    period: str | None,
    slot: dict,
) -> bool:
    parsed = _parse_slot_start(slot.get("start_time", ""))
    if parsed is None:
        return False

    slot_hour, slot_minute = parsed
    if slot_minute != minute:
        return False

    if period:
        hour_24 = hour % 12
        if period == "pm":
            hour_24 += 12
        return slot_hour == hour_24

    if hour > 12:
        return slot_hour == hour

    slot_hour_12 = slot_hour % 12 or 12
    return slot_hour_12 == hour


def _deterministic_slot_index(utterance: str, slots: list[dict]) -> int | None:
    text = _normalize_time_utterance(utterance)
    matches: set[int] = set()

    option_idx = _option_index_from_utterance(text, len(slots))
    if option_idx is not None:
        matches.add(option_idx)

    if any(word in text for word in ("noon", "midday")):
        for idx, slot in enumerate(slots):
            if _candidate_matches_slot(12, 0, "pm", slot):
                matches.add(idx)

    for match in _NUMERIC_TIME_RE.finditer(text):
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or "00")
        period = match.group("period")
        for idx, slot in enumerate(slots):
            if _candidate_matches_slot(hour, minute, period, slot):
                matches.add(idx)

    for match in _WORD_TIME_RE.finditer(text):
        word = match.group("word")
        marker = match.group("marker")
        period = match.group("period")
        prefix = text[:match.start()].rstrip()
        if word == "one" and not marker and not period and prefix.endswith("oclock"):
            continue

        hour = _NUMBER_WORDS[word]
        for idx, slot in enumerate(slots):
            if _candidate_matches_slot(hour, 0, period, slot):
                matches.add(idx)

    if len(matches) == 1:
        return next(iter(matches))
    return None


def _extract_slot_index(utterance: str, slots: list[dict]) -> int | None:
    deterministic_idx = _deterministic_slot_index(utterance, slots)
    if deterministic_idx is not None:
        return deterministic_idx

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
    doctor = _match_doctor_deterministically(state["current_utterance"], doctors)

    if not doctor:
        doctor_list = "\n".join(f"- {d['name']} ({d['specialty']})" for d in doctors)
        doctor_name = _extract_doctor(state["current_utterance"], doctor_list)
        if doctor_name:
            doctor = (
                _match_doctor_deterministically(doctor_name, doctors)
                or find_doctor_by_name(doctor_name)
            )

    if doctor:
        state["requested_doctor"] = doctor["name"]
        state["requested_doctor_id"] = doctor["id"]
        if _utterance_may_include_date(state["current_utterance"]):
            date = _extract_date(state["current_utterance"])
            if date:
                state["requested_date"] = date
                return _fetch_and_present_slots(state)

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

    inline_idx = _deterministic_slot_index(state["current_utterance"], displayed)
    if inline_idx is not None:
        return _reserve_slot_at_index(state, inline_idx)

    times = ", ".join(_fmt(s["start_time"]) for s in displayed)
    state["agent_response"] = (
        f"I have these times available on {date}: {times}. "
        "Which time works for you?"
    )
    return state


def _reserve_slot_at_index(state: CallState, idx: int) -> CallState:
    slots = state["available_slots"]
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

    return _reserve_slot_at_index(state, idx)


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
        set_last_confirmed_appointment(
            state,
            appointment_details_from_state(state, appt_id),
        )
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
