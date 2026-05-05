"""Tests for Phase 3: LangGraph workflow, routing, and agent logic."""
from unittest.mock import MagicMock, patch

import pytest

from graph.state import CallIntent, initial_call_state


# ── Helpers ──────────────────────────────────────────────────────────────────

def _state(**kwargs):
    s = initial_call_state("CA123", "MZ456", "+14155551234")
    s.update(kwargs)
    return s


def _mock_llm_response(content: str):
    resp = MagicMock()
    resp.content = content
    llm = MagicMock()
    llm.invoke.return_value = resp
    return llm


# ── State schema ─────────────────────────────────────────────────────────────

def test_initial_call_state_fields():
    state = initial_call_state("CA1", "MZ1", "+1234567890")
    assert state["call_sid"] == "CA1"
    assert state["stream_sid"] == "MZ1"
    assert state["caller_phone"] == "+1234567890"
    assert state["conversation_history"] == []
    assert state["turn_count"] == 0
    assert state["patient_verified"] is False
    assert state["escalated"] is False
    assert state["frustration_score"] == 0.0


def test_call_intent_values():
    assert CallIntent("booking") == CallIntent.BOOKING
    assert CallIntent("faq") == CallIntent.FAQ
    with pytest.raises(ValueError):
        CallIntent("invalid_intent")


# ── Router ───────────────────────────────────────────────────────────────────

def test_route_by_intent_all_paths():
    from graph.router import route_by_intent

    cases = [
        (CallIntent.BOOKING, "booking"),
        (CallIntent.RESCHEDULE, "reschedule"),
        (CallIntent.CANCEL, "cancel"),
        (CallIntent.FAQ, "faq"),
        (CallIntent.ESCALATE, "escalate"),
        (CallIntent.FAREWELL, "farewell"),
        (CallIntent.UNKNOWN, "unknown"),
    ]
    for intent, expected in cases:
        state = _state(current_intent=intent)
        assert route_by_intent(state) == expected, f"Failed for {intent}"


def test_route_after_verification_unverified_first_attempt():
    from graph.router import route_after_verification
    state = _state(patient_verified=False, verification_attempts=0, current_intent=CallIntent.BOOKING)
    assert route_after_verification(state) == "need_more_info"


def test_route_after_verification_unverified_max_attempts():
    from graph.router import route_after_verification
    state = _state(patient_verified=False, verification_attempts=2, current_intent=CallIntent.BOOKING)
    assert route_after_verification(state) == "escalate"


def test_route_after_verification_verified_routes_to_intent():
    from graph.router import route_after_verification
    for intent, expected in [(CallIntent.BOOKING, "booking"), (CallIntent.RESCHEDULE, "reschedule"), (CallIntent.CANCEL, "cancel")]:
        state = _state(patient_verified=True, verification_attempts=0, current_intent=intent)
        assert route_after_verification(state) == expected


# ── Workflow compilation ──────────────────────────────────────────────────────

def test_workflow_compiles():
    """The LangGraph graph must compile without errors."""
    from graph.workflow import build_workflow
    graph = build_workflow()
    assert graph is not None


def test_get_compiled_graph_is_cached():
    from graph.workflow import get_compiled_graph
    g1 = get_compiled_graph()
    g2 = get_compiled_graph()
    assert g1 is g2


# ── Intent agent ─────────────────────────────────────────────────────────────

def test_intent_agent_classifies_booking():
    from agents.intent_agent import intent_agent
    state = _state(current_utterance="I'd like to book an appointment with Dr. Smith")

    with patch("agents.intent_agent.get_llm", return_value=_mock_llm_response('{"intent":"booking","confidence":0.95}')):
        result = intent_agent(state)

    assert result["current_intent"] == CallIntent.BOOKING
    assert result["intent_confidence"] == 0.95
    assert CallIntent.BOOKING in result["previous_intents"]


def test_intent_agent_classifies_faq():
    from agents.intent_agent import intent_agent
    state = _state(current_utterance="What insurance do you accept?")

    with patch("agents.intent_agent.get_llm", return_value=_mock_llm_response('{"intent":"faq","confidence":0.92}')):
        result = intent_agent(state)

    assert result["current_intent"] == CallIntent.FAQ


def test_intent_agent_unknown_on_low_confidence():
    from agents.intent_agent import intent_agent
    state = _state(current_utterance="uh hmm I don't know")

    with patch("agents.intent_agent.get_llm", return_value=_mock_llm_response('{"intent":"unknown","confidence":0.3}')):
        result = intent_agent(state)

    assert result["current_intent"] == CallIntent.UNKNOWN
    assert "what you need help with" in result["agent_response"]


def test_intent_agent_unknown_on_bad_json():
    from agents.intent_agent import intent_agent
    state = _state(current_utterance="hello")

    with patch("agents.intent_agent.get_llm", return_value=_mock_llm_response("not valid json")):
        result = intent_agent(state)

    assert result["current_intent"] == CallIntent.UNKNOWN  # confidence 0.0 → unknown, not escalate


# ── FAQ agent ────────────────────────────────────────────────────────────────

def test_faq_agent_sets_response(tmp_path):
    from agents.faq_agent import faq_agent
    from rag.ingestion import ingest_clinic_knowledge
    from pathlib import Path

    knowledge_dir = Path(__file__).parent.parent / "rag" / "clinic_knowledge"
    persist_dir = str(tmp_path / "chroma")
    ingest_clinic_knowledge(knowledge_dir=knowledge_dir, persist_dir=persist_dir, collection_name="test")

    state = _state(current_utterance="What are your hours?")

    with (
        patch("agents.faq_agent.rag_query") as mock_query,
        patch("agents.faq_agent.get_llm", return_value=_mock_llm_response("We're open Monday to Friday 8 AM to 6 PM.")),
    ):
        mock_query.return_value = [{"text": "Monday to Friday: 8:00 AM – 6:00 PM", "source": "hours_and_location.md", "distance": 0.1}]
        result = faq_agent(state)

    assert result["agent_response"] == "We're open Monday to Friday 8 AM to 6 PM."
    assert result["faq_query"] == "What are your hours?"
    assert result["faq_answer"] is not None


def test_faq_agent_fallback_on_llm_error():
    from agents.faq_agent import faq_agent

    state = _state(current_utterance="What are your hours?")
    failing_llm = MagicMock()
    failing_llm.invoke.side_effect = RuntimeError("API down")

    with (
        patch("agents.faq_agent.rag_query", return_value=[]),
        patch("agents.faq_agent.get_llm", return_value=failing_llm),
    ):
        result = faq_agent(state)

    assert "480" in result["agent_response"] or "trouble" in result["agent_response"]


# ── Stub agents ───────────────────────────────────────────────────────────────

def test_sentiment_stub_returns_zero():
    from agents.sentiment_agent import sentiment_agent
    result = sentiment_agent(_state())
    assert result["frustration_score"] == 0.0


def test_escalation_agent_sets_flags():
    from agents.escalation_agent import escalation_agent
    result = escalation_agent(_state())
    assert result["escalated"] is True
    assert result["call_outcome"] == "escalated"
    assert "front desk" in result["agent_response"]


def test_stub_agents_set_response():
    from agents.cancellation_agent import cancellation_agent
    from agents.reschedule_agent import reschedule_agent

    for agent_fn in (cancellation_agent, reschedule_agent):
        result = agent_fn(_state())
        assert result["agent_response"], f"{agent_fn.__name__} did not set agent_response"


# ── Verification agent (Phase 4) ─────────────────────────────────────────────

def test_verification_verifies_patient():
    from agents.verification_agent import verification_agent

    state = _state(current_utterance="My name is John Doe, born March 5th 1990")
    mock_patient = {"id": 1, "first_name": "John", "last_name": "Doe",
                    "date_of_birth": "1990-03-05", "phone": "4805551234", "email": "j@e.com"}

    with (
        patch("agents.verification_agent.get_llm",
              return_value=_mock_llm_response('{"name": "John Doe", "dob": "1990-03-05"}')),
        patch("agents.verification_agent.lookup_patient", return_value=mock_patient),
    ):
        result = verification_agent(state)

    assert result["patient_verified"] is True
    assert result["patient_id"] == 1
    assert result["patient_name"] == "John Doe"


def test_verification_db_miss_increments_attempts():
    from agents.verification_agent import verification_agent

    state = _state(current_utterance="John Doe, March 5 1990", verification_attempts=0)

    with (
        patch("agents.verification_agent.get_llm",
              return_value=_mock_llm_response('{"name": "John Doe", "dob": "1990-03-05"}')),
        patch("agents.verification_agent.lookup_patient", return_value=None),
    ):
        result = verification_agent(state)

    assert result["patient_verified"] is False
    assert result["verification_attempts"] == 1
    assert "couldn't find" in result["agent_response"]


def test_verification_no_extraction_asks():
    from agents.verification_agent import verification_agent

    state = _state(current_utterance="I'd like to book an appointment")

    with patch("agents.verification_agent.get_llm",
               return_value=_mock_llm_response('{"name": null, "dob": null}')):
        result = verification_agent(state)

    assert result["patient_verified"] is False
    assert result["verification_attempts"] == 0  # no attempt counted when we couldn't extract
    assert "full name" in result["agent_response"] or "date of birth" in result["agent_response"]


def test_verification_llm_error_asks():
    from agents.verification_agent import verification_agent

    state = _state(current_utterance="Hello")
    bad_llm = MagicMock()
    bad_llm.invoke.side_effect = RuntimeError("timeout")

    with patch("agents.verification_agent.get_llm", return_value=bad_llm):
        result = verification_agent(state)

    assert result["patient_verified"] is False
    assert "full name" in result["agent_response"] or "date of birth" in result["agent_response"]


# ── Booking agent (Phase 4) ───────────────────────────────────────────────────

def _verified_state(**kwargs):
    s = _state(patient_verified=True, patient_id=1, patient_name="John Doe", **kwargs)
    return s


def test_booking_asks_for_doctor_when_none_extracted():
    from agents.booking_agent import booking_agent

    state = _verified_state(current_utterance="I'd like to book an appointment")
    doctors = [{"id": 1, "name": "Dr. Sarah Smith", "specialty": "General Practice"}]

    with (
        patch("agents.booking_agent.get_all_doctors", return_value=doctors),
        patch("agents.booking_agent.get_llm",
              return_value=_mock_llm_response('{"doctor_name": null}')),
    ):
        result = booking_agent(state)

    assert result["requested_doctor"] is None
    assert "Dr. Sarah Smith" in result["agent_response"]


def test_booking_extracts_doctor_and_asks_for_date():
    from agents.booking_agent import booking_agent

    state = _verified_state(current_utterance="I want to see Dr. Smith")
    doctors = [{"id": 1, "name": "Dr. Sarah Smith", "specialty": "General Practice"}]

    with (
        patch("agents.booking_agent.get_all_doctors", return_value=doctors),
        patch("agents.booking_agent.find_doctor_by_name",
              return_value={"id": 1, "name": "Dr. Sarah Smith", "specialty": "General Practice"}),
        patch("agents.booking_agent.get_llm",
              return_value=_mock_llm_response('{"doctor_name": "Dr. Sarah Smith"}')),
    ):
        result = booking_agent(state)

    assert result["requested_doctor"] == "Dr. Sarah Smith"
    assert result["requested_doctor_id"] == 1
    assert "date" in result["agent_response"].lower()


def test_booking_extracts_date_and_presents_slots():
    from agents.booking_agent import booking_agent

    state = _verified_state(
        current_utterance="this Friday",
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
    )
    slots = [
        {"slot_id": 10, "start_time": "09:00", "end_time": "09:30"},
        {"slot_id": 11, "start_time": "10:00", "end_time": "10:30"},
    ]

    with (
        patch("agents.booking_agent.get_llm",
              return_value=_mock_llm_response('{"date": "2026-05-08"}')),
        patch("agents.booking_agent.get_available_slots", return_value=slots),
    ):
        result = booking_agent(state)

    assert result["requested_date"] == "2026-05-08"
    assert len(result["available_slots"]) == 2
    assert "9:00 AM" in result["agent_response"]


def test_booking_no_slots_clears_date():
    from agents.booking_agent import booking_agent

    state = _verified_state(
        current_utterance="this Friday",
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
    )

    with (
        patch("agents.booking_agent.get_llm",
              return_value=_mock_llm_response('{"date": "2026-05-08"}')),
        patch("agents.booking_agent.get_available_slots", return_value=[]),
    ):
        result = booking_agent(state)

    assert result["requested_date"] is None
    assert "no available" in result["agent_response"].lower() or "different date" in result["agent_response"].lower()


def test_booking_locks_slot_and_asks_for_reason():
    from agents.booking_agent import booking_agent

    slots = [{"slot_id": 10, "start_time": "09:00", "end_time": "09:30"}]
    state = _verified_state(
        current_utterance="9 AM please",
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-08",
        available_slots=slots,
    )

    with (
        patch("agents.booking_agent.get_llm",
              return_value=_mock_llm_response('{"slot_index": 0}')),
        patch("agents.booking_agent.lock_slot", return_value=True),
    ):
        result = booking_agent(state)

    assert result["locked_slot_id"] == 10
    assert result["requested_time"] == "09:00"
    assert "reason" in result["agent_response"].lower()


def test_booking_slot_lock_failure_shows_remaining():
    from agents.booking_agent import booking_agent

    slots = [
        {"slot_id": 10, "start_time": "09:00", "end_time": "09:30"},
        {"slot_id": 11, "start_time": "10:00", "end_time": "10:30"},
    ]
    state = _verified_state(
        current_utterance="9 AM",
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-08",
        available_slots=slots,
    )

    with (
        patch("agents.booking_agent.get_llm",
              return_value=_mock_llm_response('{"slot_index": 0}')),
        patch("agents.booking_agent.lock_slot", return_value=False),
    ):
        result = booking_agent(state)

    assert result["locked_slot_id"] is None
    assert len(result["available_slots"]) == 1  # taken slot removed
    assert "10:00 AM" in result["agent_response"]


def test_booking_asks_for_reason_before_patient_responds():
    from agents.booking_agent import booking_agent

    # Slot is locked but last agent message wasn't asking for reason
    slots = [{"slot_id": 10, "start_time": "09:00", "end_time": "09:30"}]
    state = _verified_state(
        current_utterance="yes",
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-08",
        available_slots=slots,
        locked_slot_id=10,
        requested_time="09:00",
        # conversation_history has no agent message asking "reason for your visit"
    )

    result = booking_agent(state)

    assert result["reason_for_visit"] is None
    assert "reason" in result["agent_response"].lower()


def test_booking_confirms_appointment_after_reason():
    from agents.booking_agent import booking_agent

    slots = [{"slot_id": 10, "start_time": "09:00", "end_time": "09:30"}]
    state = _verified_state(
        current_utterance="Annual checkup",
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-08",
        available_slots=slots,
        locked_slot_id=10,
        requested_time="09:00",
        conversation_history=[
            {"role": "agent", "text": "I've reserved the 9:00 AM slot. What is the reason for your visit today?"}
        ],
    )

    with patch("agents.booking_agent.confirm_booking", return_value=42):
        result = booking_agent(state)

    assert result["booked_appointment_id"] == 42
    assert result["call_outcome"] == "booked"
    assert "confirmed" in result["agent_response"].lower() or "all set" in result["agent_response"].lower()


def test_booking_already_booked_returns_confirmation():
    from agents.booking_agent import booking_agent

    state = _verified_state(
        requested_doctor="Dr. Sarah Smith",
        requested_date="2026-05-08",
        requested_time="09:00",
        booked_appointment_id=42,
    )

    result = booking_agent(state)

    assert "Dr. Sarah Smith" in result["agent_response"]
    assert "confirmed" in result["agent_response"].lower() or "already" in result["agent_response"].lower()


# ── Cancellation agent (Phase 5) ─────────────────────────────────────────────

_APPT = {
    "id": 7,
    "doctor_id": 1,
    "doctor_name": "Dr. Sarah Smith",
    "date": "2026-05-10",
    "start_time": "09:00",
    "reason": "Annual checkup",
}


def test_cancellation_cancels_appointment():
    from agents.cancellation_agent import cancellation_agent

    state = _verified_state()

    with (
        patch("agents.cancellation_agent.get_patient_appointments", return_value=[_APPT]),
        patch("agents.cancellation_agent.cancel_appointment"),
    ):
        result = cancellation_agent(state)

    assert result["existing_appointment_id"] == 7
    assert result["call_outcome"] == "cancelled"
    assert "Dr. Sarah Smith" in result["agent_response"]
    assert "cancelled" in result["agent_response"].lower()


def test_cancellation_no_appointments():
    from agents.cancellation_agent import cancellation_agent

    state = _verified_state()

    with patch("agents.cancellation_agent.get_patient_appointments", return_value=[]):
        result = cancellation_agent(state)

    assert result["existing_appointment_id"] is None
    assert result["call_outcome"] is None
    assert "don't see" in result["agent_response"].lower() or "no" in result["agent_response"].lower()


def test_cancellation_db_error_returns_fallback():
    from agents.cancellation_agent import cancellation_agent

    state = _verified_state()

    with (
        patch("agents.cancellation_agent.get_patient_appointments", return_value=[_APPT]),
        patch("agents.cancellation_agent.cancel_appointment", side_effect=RuntimeError("db locked")),
    ):
        result = cancellation_agent(state)

    assert result["call_outcome"] is None
    assert "480" in result["agent_response"] or "trouble" in result["agent_response"]


# ── Reschedule agent (Phase 5) ────────────────────────────────────────────────

def test_reschedule_cancels_old_and_asks_for_date():
    from agents.reschedule_agent import reschedule_agent

    state = _verified_state()

    with (
        patch("agents.reschedule_agent.get_patient_appointments", return_value=[_APPT]),
        patch("agents.reschedule_agent.cancel_appointment"),
    ):
        result = reschedule_agent(state)

    assert result["existing_appointment_id"] == 7
    assert result["requested_doctor"] == "Dr. Sarah Smith"
    assert result["requested_doctor_id"] == 1
    assert "date" in result["agent_response"].lower()


def test_reschedule_no_appointments():
    from agents.reschedule_agent import reschedule_agent

    state = _verified_state()

    with patch("agents.reschedule_agent.get_patient_appointments", return_value=[]):
        result = reschedule_agent(state)

    assert result["existing_appointment_id"] is None
    assert "don't see" in result["agent_response"].lower() or "no" in result["agent_response"].lower()


def test_reschedule_delegates_to_booking_after_cancel():
    from agents.reschedule_agent import reschedule_agent

    # existing_appointment_id already set → should delegate to booking
    slots = [{"slot_id": 10, "start_time": "09:00", "end_time": "09:30"}]
    state = _verified_state(
        current_utterance="this Friday",
        existing_appointment_id=7,
        existing_appointment_details=_APPT,
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
    )

    with (
        patch("agents.booking_agent.get_llm",
              return_value=_mock_llm_response('{"date": "2026-05-08"}')),
        patch("agents.booking_agent.get_available_slots", return_value=slots),
    ):
        result = reschedule_agent(state)

    # Booking agent should have picked up and fetched slots
    assert result["requested_date"] == "2026-05-08"
    assert len(result["available_slots"]) == 1


def test_reschedule_db_error_returns_fallback():
    from agents.reschedule_agent import reschedule_agent

    state = _verified_state()

    with (
        patch("agents.reschedule_agent.get_patient_appointments", return_value=[_APPT]),
        patch("agents.reschedule_agent.cancel_appointment", side_effect=RuntimeError("db locked")),
    ):
        result = reschedule_agent(state)

    assert result["existing_appointment_id"] is None
    assert "480" in result["agent_response"] or "trouble" in result["agent_response"]


# ── Sentiment agent (Phase 6) ─────────────────────────────────────────────────

def test_sentiment_scores_frustration():
    from agents.sentiment_agent import sentiment_agent
    state = _state(current_utterance="This is absolutely ridiculous and terrible")
    result = sentiment_agent(state)
    assert result["frustration_score"] > 0.0


def test_sentiment_auto_escalates_on_threshold():
    from agents.sentiment_agent import sentiment_agent
    state = _state(
        current_utterance="I want to speak to a manager right now",
        frustration_score=0.4,
    )
    result = sentiment_agent(state)
    assert result["current_intent"] == CallIntent.ESCALATE
    assert result["guardrail_triggered"] == "frustration"


def test_sentiment_abuse_escalates_immediately():
    from agents.sentiment_agent import sentiment_agent
    state = _state(current_utterance="you are so stupid and useless")
    result = sentiment_agent(state)
    assert result["guardrail_triggered"] == "abuse"
    assert result["current_intent"] == CallIntent.ESCALATE


def test_sentiment_neutral_utterance_no_escalation():
    from agents.sentiment_agent import sentiment_agent
    state = _state(current_utterance="I'd like to book an appointment please")
    result = sentiment_agent(state)
    assert result["guardrail_triggered"] is None
    assert result["frustration_score"] == 0.0


def test_intent_agent_skips_when_guardrail_triggered():
    from agents.intent_agent import intent_agent
    state = _state(guardrail_triggered="abuse", current_intent=CallIntent.ESCALATE)
    # LLM should NOT be called
    with patch("agents.intent_agent.get_llm") as mock_llm:
        result = intent_agent(state)
        mock_llm.assert_not_called()
    assert result["current_intent"] == CallIntent.ESCALATE


# ── Escalation agent with summary (Phase 6) ──────────────────────────────────

def test_escalation_agent_builds_summary():
    from agents.escalation_agent import escalation_agent
    state = _state(
        patient_name="John Doe",
        previous_intents=[CallIntent.BOOKING],
        requested_doctor="Dr. Sarah Smith",
        turn_count=4,
    )
    result = escalation_agent(state)
    assert result["call_summary"] is not None
    assert "booking" in result["call_summary"].lower()
    assert result["escalated"] is True


def test_escalation_abuse_uses_brief_response():
    from agents.escalation_agent import escalation_agent
    state = _state(guardrail_triggered="abuse")
    result = escalation_agent(state)
    assert "transfer" in result["agent_response"].lower()


# ── Guardrails (Phase 6) ──────────────────────────────────────────────────────

def test_pii_masker_masks_phone():
    from guardrails.pii_masker import mask_pii
    assert mask_pii("call me at 480-555-1234") == "call me at [PHONE]"


def test_pii_masker_masks_dob():
    from guardrails.pii_masker import mask_pii
    assert "[DOB]" in mask_pii("born on 1990-03-05")


def test_pii_masker_masks_email():
    from guardrails.pii_masker import mask_pii
    assert "[EMAIL]" in mask_pii("email me at john@example.com")


def test_scope_detector_clinic_topic():
    from guardrails.scope_detector import is_in_scope
    assert is_in_scope("What are your hours?") is True
    assert is_in_scope("Can I book an appointment?") is True


def test_scope_detector_off_topic():
    from guardrails.scope_detector import is_in_scope
    assert is_in_scope("What is the weather today?") is False


def test_abuse_detector_flags_abuse():
    from guardrails.abuse_detector import is_abusive
    assert is_abusive("you are so stupid") is True
    assert is_abusive("I'd like to schedule a visit") is False
