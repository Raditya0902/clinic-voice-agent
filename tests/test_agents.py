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
    assert state["active_appointment_workflow"] is None
    assert state["last_confirmed_appointment_id"] is None
    assert state["last_confirmed_appointment_details"] is None


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


def test_intent_agent_unknown_at_boundary_sets_fallback():
    from agents.intent_agent import intent_agent

    state = _state(
        current_utterance="hmm",
        agent_response="Done! Your appointment has been cancelled.",
    )

    with patch("agents.intent_agent.get_llm", return_value=_mock_llm_response('{"intent":"unknown","confidence":0.5}')):
        result = intent_agent(state)

    assert result["current_intent"] == CallIntent.UNKNOWN
    assert "what you need help with" in result["agent_response"]
    assert "cancelled" not in result["agent_response"].lower()


def test_intent_agent_marks_out_of_scope_unknown():
    from agents.intent_agent import intent_agent
    state = _state(current_utterance="What is the weather today?")

    with patch("agents.intent_agent.get_llm", return_value=_mock_llm_response('{"intent":"unknown","confidence":0.2}')):
        result = intent_agent(state)

    assert result["current_intent"] == CallIntent.UNKNOWN
    assert result["guardrail_triggered"] == "out_of_scope"
    assert "appointments" in result["agent_response"]


def test_intent_agent_recovers_after_out_of_scope_turn():
    from agents.intent_agent import intent_agent
    state = _state(current_utterance="I need to book an appointment", guardrail_triggered="out_of_scope")

    with patch("agents.intent_agent.get_llm", return_value=_mock_llm_response('{"intent":"booking","confidence":0.9}')):
        result = intent_agent(state)

    assert result["guardrail_triggered"] is None
    assert result["current_intent"] == CallIntent.BOOKING


def test_intent_agent_routes_pending_cancellation_confirmation_without_llm():
    from agents.intent_agent import intent_agent

    state = _verified_state(
        current_utterance="yes",
        existing_appointment_id=7,
        existing_appointment_details={"id": 7},
        conversation_history=[
            {
                "role": "agent",
                "text": "I found your 9:00 AM appointment. Should I cancel this appointment?",
            },
            {"role": "patient", "text": "yes"},
        ],
    )

    with patch("agents.intent_agent.get_llm") as mock_get_llm:
        result = intent_agent(state)

    mock_get_llm.assert_not_called()
    assert result["current_intent"] == CallIntent.CANCEL
    assert result["intent_confidence"] == 1.0


def test_intent_agent_routes_no_after_anything_else_to_farewell_without_llm():
    from agents.intent_agent import intent_agent

    state = _state(
        current_utterance="no",
        conversation_history=[
            {
                "role": "agent",
                "text": "Is there anything else I can help you with?",
            },
            {"role": "patient", "text": "no"},
        ],
    )

    with patch("agents.intent_agent.get_llm") as mock_get_llm:
        result = intent_agent(state)

    mock_get_llm.assert_not_called()
    assert result["current_intent"] == CallIntent.FAREWELL
    assert result["intent_confidence"] == 1.0


def test_intent_agent_keeps_active_booking_on_slot_prompt_without_llm():
    from agents.intent_agent import intent_agent

    state = _verified_state(
        current_utterance="11 AM",
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-07",
        available_slots=[{"slot_id": 1, "start_time": "11:00"}],
        conversation_history=[
            {
                "role": "agent",
                "text": "I have these times available on 2026-05-07: 8:00 AM, 9:00 AM, 10:00 AM, 11:00 AM. Which time works for you?",
            },
            {"role": "patient", "text": "11 AM"},
        ],
    )

    with patch("agents.intent_agent.get_llm") as mock_get_llm:
        result = intent_agent(state)

    mock_get_llm.assert_not_called()
    assert result["current_intent"] == CallIntent.BOOKING
    assert result["intent_confidence"] == 1.0


def test_intent_agent_keeps_active_booking_on_doctor_prompt_without_llm():
    from agents.intent_agent import intent_agent

    state = _verified_state(
        current_utterance="Dr. Smith",
        current_intent=CallIntent.BOOKING,
        requested_doctor=None,
        conversation_history=[
            {
                "role": "agent",
                "text": "Which doctor would you like to see? We have: Dr. Sarah Smith.",
            },
            {"role": "patient", "text": "Dr. Smith"},
        ],
    )

    with patch("agents.intent_agent.get_llm") as mock_get_llm:
        result = intent_agent(state)

    mock_get_llm.assert_not_called()
    assert result["current_intent"] == CallIntent.BOOKING
    assert result["intent_confidence"] == 1.0


def test_intent_agent_keeps_active_reschedule_on_slot_prompt_without_llm():
    from agents.intent_agent import intent_agent

    state = _verified_state(
        current_utterance="10 AM",
        existing_appointment_id=7,
        existing_appointment_details={"id": 7, "doctor_name": "Dr. Sarah Smith"},
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-12",
        available_slots=[{"slot_id": 2, "start_time": "10:00"}],
        conversation_history=[
            {
                "role": "agent",
                "text": "I have these times available on 2026-05-12: 8:00 AM, 9:00 AM, 10:00 AM, 11:00 AM. Which time works for you?",
            },
            {"role": "patient", "text": "10 AM"},
        ],
    )

    with patch("agents.intent_agent.get_llm") as mock_get_llm:
        result = intent_agent(state)

    mock_get_llm.assert_not_called()
    assert result["current_intent"] == CallIntent.RESCHEDULE
    assert result["intent_confidence"] == 1.0


def test_intent_agent_starts_fresh_booking_after_prior_booking():
    from agents.intent_agent import intent_agent

    state = _verified_state(
        current_utterance="I need to book another appointment",
        current_intent=CallIntent.BOOKING,
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-08",
        requested_time="09:00",
        reason_for_visit="Annual checkup",
        available_slots=[{"slot_id": 10, "start_time": "09:00"}],
        locked_slot_id=10,
        booked_appointment_id=42,
        last_confirmed_appointment_id=42,
        last_confirmed_appointment_details={
            "id": 42,
            "doctor_id": 1,
            "doctor_name": "Dr. Sarah Smith",
            "date": "2026-05-08",
            "start_time": "09:00",
            "reason": "Annual checkup",
        },
        call_outcome="booked",
    )

    with (
        patch("agents.intent_agent.get_llm",
              return_value=_mock_llm_response('{"intent":"booking","confidence":0.96}')),
        patch("agents.appointment_workflow.release_slot") as mock_release,
    ):
        result = intent_agent(state)

    mock_release.assert_not_called()
    assert result["current_intent"] == CallIntent.BOOKING
    assert result["active_appointment_workflow"] == "booking"
    assert result["booked_appointment_id"] is None
    assert result["requested_doctor"] is None
    assert result["requested_date"] is None
    assert result["call_outcome"] is None
    assert result["last_confirmed_appointment_id"] == 42


def test_intent_agent_releases_unconfirmed_lock_when_switching_workflows():
    from agents.intent_agent import intent_agent

    state = _verified_state(
        current_utterance="Actually cancel my appointment",
        current_intent=CallIntent.BOOKING,
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-08",
        requested_time="09:00",
        available_slots=[{"slot_id": 10, "start_time": "09:00"}],
        locked_slot_id=10,
        booked_appointment_id=None,
    )

    with (
        patch("agents.intent_agent.get_llm",
              return_value=_mock_llm_response('{"intent":"cancel","confidence":0.94}')),
        patch("agents.appointment_workflow.release_slot") as mock_release,
    ):
        result = intent_agent(state)

    mock_release.assert_called_once_with(10, "CA123")
    assert result["active_appointment_workflow"] == "cancel"
    assert result["locked_slot_id"] is None
    assert result["available_slots"] == []


# ── FAQ agent ────────────────────────────────────────────────────────────────

def test_faq_agent_markdown_mode_skips_chroma_by_default(monkeypatch):
    from agents.faq_agent import faq_agent

    monkeypatch.delenv("FAQ_RETRIEVAL_MODE", raising=False)
    state = _state(current_utterance="What are your hours?")

    with (
        patch("agents.faq_agent.rag_query") as mock_rag_query,
        patch("agents.faq_agent.get_llm", return_value=_mock_llm_response("We're open Monday to Friday 8 AM to 6 PM.")),
    ):
        result = faq_agent(state)

    mock_rag_query.assert_not_called()
    assert result["agent_response"] == "We're open Monday to Friday 8 AM to 6 PM."
    assert result["faq_query"] == "What are your hours?"
    assert result["faq_answer"] is not None
    assert result["call_outcome"] == "faq_answered"


def test_faq_agent_chroma_mode_uses_rag_query(monkeypatch):
    from agents.faq_agent import faq_agent

    monkeypatch.setenv("FAQ_RETRIEVAL_MODE", "chroma")
    state = _state(current_utterance="What are your hours?")

    with (
        patch("agents.faq_agent.rag_query") as mock_rag_query,
        patch("agents.faq_agent.get_llm", return_value=_mock_llm_response("We're open Monday to Friday 8 AM to 6 PM.")),
    ):
        mock_rag_query.return_value = [
            {"text": "Monday to Friday: 8:00 AM - 6:00 PM", "source": "hours_and_location.md", "distance": 0.1}
        ]
        result = faq_agent(state)

    mock_rag_query.assert_called_once_with("What are your hours?", top_k=3)
    assert result["agent_response"] == "We're open Monday to Friday 8 AM to 6 PM."


def test_faq_agent_sets_faq_answered_outcome_when_none(monkeypatch):
    from agents.faq_agent import faq_agent

    monkeypatch.delenv("FAQ_RETRIEVAL_MODE", raising=False)
    state = _state(current_utterance="Where are you located?")

    with patch(
        "agents.faq_agent.get_llm",
        return_value=_mock_llm_response("We're at 123 Wellness Avenue in Phoenix."),
    ):
        result = faq_agent(state)

    assert result["call_outcome"] == "faq_answered"


@pytest.mark.parametrize("outcome", ["booked", "cancelled", "rescheduled", "escalated"])
def test_faq_agent_does_not_overwrite_existing_outcomes(monkeypatch, outcome):
    from agents.faq_agent import faq_agent

    monkeypatch.delenv("FAQ_RETRIEVAL_MODE", raising=False)
    state = _state(current_utterance="What are your hours?", call_outcome=outcome)

    with patch(
        "agents.faq_agent.get_llm",
        return_value=_mock_llm_response("We're open Monday to Friday, 8 AM to 6 PM."),
    ):
        result = faq_agent(state)

    assert result["call_outcome"] == outcome


def test_faq_agent_prompt_is_concise_for_phone(monkeypatch):
    from agents.faq_agent import faq_agent

    monkeypatch.delenv("FAQ_RETRIEVAL_MODE", raising=False)
    state = _state(current_utterance="Do you take Aetna?")
    llm = _mock_llm_response("Yes, we accept Aetna PPO and HMO plans.")

    with patch("agents.faq_agent.get_llm", return_value=llm):
        faq_agent(state)

    messages = llm.invoke.call_args.args[0]
    system_prompt = messages[0]["content"]
    assert "1-2 short phone-friendly sentences" in system_prompt
    assert "2-3 sentences" not in system_prompt


def test_faq_agent_unavailable_answer_uses_front_desk_fallback_only():
    from agents.faq_agent import FRONT_DESK_FALLBACK, faq_agent

    state = _state(current_utterance="Do you have valet parking?")

    with (
        patch("agents.faq_agent._safe_rag_context", return_value="No relevant information found."),
        patch("agents.faq_agent.get_llm") as mock_get_llm,
    ):
        result = faq_agent(state)

    mock_get_llm.assert_not_called()
    assert result["agent_response"] == FRONT_DESK_FALLBACK


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


def test_faq_agent_survives_rag_base_exception(monkeypatch):
    from agents.faq_agent import faq_agent

    class PanicLike(BaseException):
        pass

    monkeypatch.setenv("FAQ_RETRIEVAL_MODE", "chroma")
    state = _state(current_utterance="What are your hours?")

    with (
        patch("agents.faq_agent.rag_query", side_effect=PanicLike("rust panic")),
        patch("agents.faq_agent.get_llm", return_value=_mock_llm_response("Please call the front desk for that detail.")),
    ):
        result = faq_agent(state)

    assert result["agent_response"] == "Please call the front desk for that detail."
    assert result["faq_answer"] is not None


# ── Dashboard status mapping ─────────────────────────────────────────────────

def test_dashboard_status_mapping_labels_faq_answered():
    from dashboard.status import format_status, label_for_outcome

    assert label_for_outcome("faq_answered") == "FAQ Answered"
    assert "FAQ Answered" in format_status("faq_answered")
    assert "Unknown" not in format_status("faq_answered")
    assert label_for_outcome("completed") == "Completed"


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


@pytest.mark.parametrize(
    ("utterance", "expected_name"),
    [
        ("Dr. Raj Patel", "Dr. Raj Patel"),
        ("Raj Patel", "Dr. Raj Patel"),
        ("Dr Patel", "Dr. Raj Patel"),
        ("Patel", "Dr. Raj Patel"),
        ("Raj", "Dr. Raj Patel"),
        ("Doctor Chen", "Dr. Michael Chen"),
        ("Emily", "Dr. Emily Johnson"),
        ("the first one", "Dr. Sarah Smith"),
        ("number two", "Dr. Raj Patel"),
    ],
)
def test_booking_deterministic_doctor_match_accepts_common_name_forms(utterance, expected_name):
    from agents.booking_agent import _match_doctor_deterministically

    doctors = [
        {"id": 1, "name": "Dr. Sarah Smith", "specialty": "General Practice"},
        {"id": 2, "name": "Dr. Raj Patel", "specialty": "Internal Medicine"},
        {"id": 3, "name": "Dr. Emily Johnson", "specialty": "Pediatrics"},
        {"id": 4, "name": "Dr. Michael Chen", "specialty": "Dermatology"},
    ]

    result = _match_doctor_deterministically(utterance, doctors)

    assert result is not None
    assert result["name"] == expected_name


def test_booking_resolves_llm_partial_doctor_name_with_deterministic_match():
    from agents.booking_agent import booking_agent

    state = _verified_state(current_utterance="I want the doctor")
    doctors = [
        {"id": 1, "name": "Dr. Sarah Smith", "specialty": "General Practice"},
        {"id": 2, "name": "Dr. Raj Patel", "specialty": "Internal Medicine"},
    ]

    with (
        patch("agents.booking_agent.get_all_doctors", return_value=doctors),
        patch("agents.booking_agent.get_llm",
              return_value=_mock_llm_response('{"doctor_name": "Dr. Smith"}')),
        patch("agents.booking_agent.find_doctor_by_name") as mock_find_doctor,
    ):
        result = booking_agent(state)

    mock_find_doctor.assert_not_called()
    assert result["requested_doctor"] == "Dr. Sarah Smith"
    assert result["requested_doctor_id"] == 1


@pytest.mark.parametrize("utterance", ["Dr Smith", "Sarah"])
def test_booking_deterministic_doctor_match_avoids_ambiguous_names(utterance):
    from agents.booking_agent import _match_doctor_deterministically

    doctors = [
        {"id": 1, "name": "Dr. Sarah Smith", "specialty": "General Practice"},
        {"id": 2, "name": "Dr. Raj Smith", "specialty": "Internal Medicine"},
        {"id": 3, "name": "Dr. Sarah Johnson", "specialty": "Pediatrics"},
    ]

    assert _match_doctor_deterministically(utterance, doctors) is None


def test_booking_uses_deterministic_doctor_match_before_llm():
    from agents.booking_agent import booking_agent

    state = _verified_state(current_utterance="Dr Patel")
    doctors = [
        {"id": 1, "name": "Dr. Sarah Smith", "specialty": "General Practice"},
        {"id": 2, "name": "Dr. Raj Patel", "specialty": "Internal Medicine"},
        {"id": 3, "name": "Dr. Emily Johnson", "specialty": "Pediatrics"},
        {"id": 4, "name": "Dr. Michael Chen", "specialty": "Dermatology"},
    ]

    with (
        patch("agents.booking_agent.get_all_doctors", return_value=doctors),
        patch("agents.booking_agent.find_doctor_by_name") as mock_find_doctor,
        patch("agents.booking_agent.get_llm") as mock_get_llm,
    ):
        result = booking_agent(state)

    mock_get_llm.assert_not_called()
    mock_find_doctor.assert_not_called()
    assert result["requested_doctor"] == "Dr. Raj Patel"
    assert result["requested_doctor_id"] == 2
    assert "date" in result["agent_response"].lower()


def test_booking_doctor_stage_reserves_inline_date_time():
    from agents.booking_agent import booking_agent

    state = _verified_state(current_utterance="Dr. Chen tomorrow at 9 AM")
    doctors = [
        {"id": 1, "name": "Dr. Sarah Smith", "specialty": "General Practice"},
        {"id": 4, "name": "Dr. Michael Chen", "specialty": "Dermatology"},
    ]
    slots = [
        {"slot_id": 10, "start_time": "08:00", "end_time": "08:30"},
        {"slot_id": 11, "start_time": "09:00", "end_time": "09:30"},
    ]

    with (
        patch("agents.booking_agent.get_all_doctors", return_value=doctors),
        patch("agents.booking_agent.get_llm",
              return_value=_mock_llm_response('{"date": "2026-05-08"}')),
        patch("agents.booking_agent.get_available_slots", return_value=slots),
        patch("agents.booking_agent.lock_slot", return_value=True),
    ):
        result = booking_agent(state)

    assert result["requested_doctor"] == "Dr. Michael Chen"
    assert result["requested_doctor_id"] == 4
    assert result["requested_date"] == "2026-05-08"
    assert result["locked_slot_id"] == 11
    assert result["requested_time"] == "09:00"
    assert "reserved the 9:00 AM slot" in result["agent_response"]


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


def test_booking_date_stage_reserves_inline_requested_time():
    from agents.booking_agent import booking_agent

    state = _verified_state(
        current_utterance="tomorrow at 9 AM",
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
    )
    slots = [
        {"slot_id": 10, "start_time": "08:00", "end_time": "08:30"},
        {"slot_id": 11, "start_time": "09:00", "end_time": "09:30"},
    ]

    with (
        patch("agents.booking_agent.get_llm",
              return_value=_mock_llm_response('{"date": "2026-05-08"}')),
        patch("agents.booking_agent.get_available_slots", return_value=slots),
        patch("agents.booking_agent.lock_slot", return_value=True),
    ):
        result = booking_agent(state)

    assert result["requested_date"] == "2026-05-08"
    assert result["locked_slot_id"] == 11
    assert result["requested_time"] == "09:00"
    assert "reserved the 9:00 AM slot" in result["agent_response"]
    assert "I have these times available" not in result["agent_response"]


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


@pytest.mark.parametrize(
    "utterance",
    ["10", "10 AM", "ten", "ten AM", "ten o'clock", "the 10 o'clock one"],
)
def test_booking_slot_parser_maps_common_time_forms(utterance):
    from agents.booking_agent import _deterministic_slot_index

    slots = [
        {"slot_id": 10, "start_time": "09:00", "end_time": "09:30"},
        {"slot_id": 11, "start_time": "10:00", "end_time": "10:30"},
    ]

    assert _deterministic_slot_index(utterance, slots) == 1


def test_booking_slot_parser_rejects_unoffered_time():
    from agents.booking_agent import _deterministic_slot_index

    slots = [
        {"slot_id": 10, "start_time": "09:00", "end_time": "09:30"},
        {"slot_id": 11, "start_time": "10:00", "end_time": "10:30"},
    ]

    assert _deterministic_slot_index("11 AM", slots) is None


@pytest.mark.parametrize(
    ("utterance", "expected_idx"),
    [
        ("the first one", 0),
        ("second", 1),
        ("number two", 1),
        ("last one", 2),
        ("earliest", 0),
        ("latest", 2),
    ],
)
def test_booking_slot_parser_maps_option_words(utterance, expected_idx):
    from agents.booking_agent import _deterministic_slot_index

    slots = [
        {"slot_id": 10, "start_time": "09:00", "end_time": "09:30"},
        {"slot_id": 11, "start_time": "10:00", "end_time": "10:30"},
        {"slot_id": 12, "start_time": "12:00", "end_time": "12:30"},
    ]

    assert _deterministic_slot_index(utterance, slots) == expected_idx


@pytest.mark.parametrize("utterance", ["noon", "midday"])
def test_booking_slot_parser_maps_noon_words(utterance):
    from agents.booking_agent import _deterministic_slot_index

    slots = [
        {"slot_id": 10, "start_time": "09:00", "end_time": "09:30"},
        {"slot_id": 12, "start_time": "12:00", "end_time": "12:30"},
    ]

    assert _deterministic_slot_index(utterance, slots) == 1


def test_booking_locks_spoken_slot_without_llm():
    from agents.booking_agent import booking_agent

    slots = [
        {"slot_id": 10, "start_time": "09:00", "end_time": "09:30"},
        {"slot_id": 11, "start_time": "10:00", "end_time": "10:30"},
    ]
    state = _verified_state(
        current_utterance="the 10 o'clock one",
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-08",
        available_slots=slots,
    )

    with (
        patch("agents.booking_agent.get_llm") as mock_get_llm,
        patch("agents.booking_agent.lock_slot", return_value=True),
    ):
        result = booking_agent(state)

    mock_get_llm.assert_not_called()
    assert result["locked_slot_id"] == 11
    assert result["requested_time"] == "10:00"


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
    assert result["last_confirmed_appointment_id"] == 42
    assert result["last_confirmed_appointment_details"] == {
        "id": 42,
        "doctor_id": 1,
        "doctor_name": "Dr. Sarah Smith",
        "date": "2026-05-08",
        "start_time": "09:00",
        "reason": "Annual checkup",
    }
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


def test_booking_after_prior_booking_starts_fresh_after_intent_reset():
    from agents.booking_agent import booking_agent
    from agents.intent_agent import intent_agent

    state = _verified_state(
        current_utterance="I need to book another appointment",
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-08",
        requested_time="09:00",
        reason_for_visit="Annual checkup",
        locked_slot_id=10,
        booked_appointment_id=42,
        last_confirmed_appointment_id=42,
        last_confirmed_appointment_details={
            "id": 42,
            "doctor_id": 1,
            "doctor_name": "Dr. Sarah Smith",
            "date": "2026-05-08",
            "start_time": "09:00",
            "reason": "Annual checkup",
        },
        call_outcome="booked",
    )
    doctors = [{"id": 1, "name": "Dr. Sarah Smith", "specialty": "General Practice"}]

    with patch("agents.intent_agent.get_llm",
               return_value=_mock_llm_response('{"intent":"booking","confidence":0.95}')):
        state = intent_agent(state)

    with (
        patch("agents.booking_agent.get_all_doctors", return_value=doctors),
        patch("agents.booking_agent.get_llm",
              return_value=_mock_llm_response('{"doctor_name": null}')),
    ):
        result = booking_agent(state)

    assert result["booked_appointment_id"] is None
    assert "already confirmed" not in result["agent_response"].lower()
    assert "Which doctor" in result["agent_response"]
    assert result["last_confirmed_appointment_id"] == 42


# ── Cancellation agent (Phase 5) ─────────────────────────────────────────────

_APPT = {
    "id": 7,
    "doctor_id": 1,
    "doctor_name": "Dr. Sarah Smith",
    "date": "2026-05-10",
    "start_time": "09:00",
    "reason": "Annual checkup",
}

_LATEST_APPT = {
    "id": 99,
    "doctor_id": 2,
    "doctor_name": "Dr. Raj Patel",
    "date": "2026-05-12",
    "start_time": "10:00",
    "reason": "Follow-up",
}


def test_cancellation_asks_before_cancelling_appointment():
    from agents.cancellation_agent import cancellation_agent

    state = _verified_state()

    with (
        patch("agents.cancellation_agent.get_patient_appointments", return_value=[_APPT]),
        patch("agents.cancellation_agent.cancel_appointment") as mock_cancel,
    ):
        result = cancellation_agent(state)

    assert result["existing_appointment_id"] == 7
    assert result["call_outcome"] is None
    mock_cancel.assert_not_called()
    assert "Dr. Sarah Smith" in result["agent_response"]
    assert "should i cancel" in result["agent_response"].lower()


def test_cancellation_targets_latest_confirmed_appointment_before_db_lookup():
    from agents.cancellation_agent import cancellation_agent

    state = _verified_state(
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-08",
        requested_time="09:00",
        booked_appointment_id=42,
        last_confirmed_appointment_id=99,
        last_confirmed_appointment_details=_LATEST_APPT,
        call_outcome="booked",
    )

    with (
        patch("agents.cancellation_agent.get_patient_appointments") as mock_get_appointments,
        patch("agents.cancellation_agent.cancel_appointment") as mock_cancel,
    ):
        result = cancellation_agent(state)

    mock_get_appointments.assert_not_called()
    mock_cancel.assert_not_called()
    assert result["existing_appointment_id"] == 99
    assert result["existing_appointment_details"] == _LATEST_APPT
    assert result["booked_appointment_id"] is None
    assert result["call_outcome"] == "booked"
    assert "Dr. Raj Patel" in result["agent_response"]


def test_cancellation_confirms_pending_appointment():
    from agents.cancellation_agent import cancellation_agent

    state = _verified_state(
        current_utterance="yes, cancel it",
        existing_appointment_id=7,
        existing_appointment_details=_APPT,
        last_confirmed_appointment_id=7,
        last_confirmed_appointment_details=_APPT,
        call_outcome="booked",
    )

    with patch("agents.cancellation_agent.cancel_appointment") as mock_cancel:
        result = cancellation_agent(state)

    mock_cancel.assert_called_once_with(7)
    assert result["call_outcome"] == "cancelled"
    assert result["existing_appointment_id"] is None
    assert result["existing_appointment_details"] is None
    assert result["last_confirmed_appointment_id"] is None
    assert result["last_confirmed_appointment_details"] is None
    assert "cancelled" in result["agent_response"].lower()


def test_cancellation_negative_keeps_pending_appointment():
    from agents.cancellation_agent import cancellation_agent

    state = _verified_state(
        current_utterance="no, keep it",
        existing_appointment_id=7,
        existing_appointment_details=_APPT,
        last_confirmed_appointment_id=7,
        last_confirmed_appointment_details=_APPT,
        call_outcome="booked",
    )

    with patch("agents.cancellation_agent.cancel_appointment") as mock_cancel:
        result = cancellation_agent(state)

    mock_cancel.assert_not_called()
    assert result["existing_appointment_id"] is None
    assert result["existing_appointment_details"] is None
    assert result["last_confirmed_appointment_id"] == 7
    assert result["last_confirmed_appointment_details"] == _APPT
    assert result["call_outcome"] == "booked"
    assert "leave that appointment" in result["agent_response"].lower()


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

    state = _verified_state(
        current_utterance="yes",
        existing_appointment_id=7,
        existing_appointment_details=_APPT,
    )

    with (
        patch("agents.cancellation_agent.cancel_appointment", side_effect=RuntimeError("db locked")),
    ):
        result = cancellation_agent(state)

    assert result["call_outcome"] is None
    assert "480" in result["agent_response"] or "trouble" in result["agent_response"]


# ── Reschedule agent (Phase 5) ────────────────────────────────────────────────

def test_reschedule_keeps_old_and_asks_for_date():
    from agents.reschedule_agent import reschedule_agent

    state = _verified_state()

    with (
        patch("agents.reschedule_agent.get_patient_appointments", return_value=[_APPT]),
        patch("agents.reschedule_agent.cancel_appointment") as mock_cancel,
    ):
        result = reschedule_agent(state)

    mock_cancel.assert_not_called()
    assert result["existing_appointment_id"] == 7
    assert result["requested_doctor"] == "Dr. Sarah Smith"
    assert result["requested_doctor_id"] == 1
    assert "keep that appointment" in result["agent_response"].lower()
    assert "date" in result["agent_response"].lower()


def test_reschedule_targets_latest_confirmed_appointment_before_db_lookup():
    from agents.reschedule_agent import reschedule_agent

    state = _verified_state(
        last_confirmed_appointment_id=99,
        last_confirmed_appointment_details=_LATEST_APPT,
        call_outcome="booked",
    )

    with (
        patch("agents.reschedule_agent.get_patient_appointments") as mock_get_appointments,
        patch("agents.reschedule_agent.cancel_appointment") as mock_cancel,
    ):
        result = reschedule_agent(state)

    mock_get_appointments.assert_not_called()
    mock_cancel.assert_not_called()
    assert result["existing_appointment_id"] == 99
    assert result["existing_appointment_details"] == _LATEST_APPT
    assert result["requested_doctor"] == "Dr. Raj Patel"
    assert result["requested_doctor_id"] == 2
    assert "10:00 AM" in result["agent_response"]


def test_reschedule_after_prior_booking_clears_stale_replacement_state():
    from agents.reschedule_agent import reschedule_agent

    state = _verified_state(
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-08",
        requested_time="09:00",
        reason_for_visit="Annual checkup",
        booked_appointment_id=42,
        last_confirmed_appointment_id=42,
        last_confirmed_appointment_details={
            "id": 42,
            "doctor_id": 1,
            "doctor_name": "Dr. Sarah Smith",
            "date": "2026-05-08",
            "start_time": "09:00",
            "reason": "Annual checkup",
        },
        call_outcome="booked",
    )

    with patch("agents.reschedule_agent.cancel_appointment") as mock_cancel:
        result = reschedule_agent(state)

    mock_cancel.assert_not_called()
    assert result["existing_appointment_id"] == 42
    assert result["booked_appointment_id"] is None
    assert result["requested_date"] is None
    assert result["requested_time"] is None
    assert result["reason_for_visit"] is None
    assert "What date" in result["agent_response"]


def test_reschedule_no_appointments():
    from agents.reschedule_agent import reschedule_agent

    state = _verified_state()

    with patch("agents.reschedule_agent.get_patient_appointments", return_value=[]):
        result = reschedule_agent(state)

    assert result["existing_appointment_id"] is None
    assert "don't see" in result["agent_response"].lower() or "no" in result["agent_response"].lower()


def test_reschedule_ignores_cancelled_appointment_state():
    from agents.reschedule_agent import reschedule_agent

    state = _verified_state(
        existing_appointment_id=7,
        existing_appointment_details=_APPT,
        call_outcome="cancelled",
    )

    with patch("agents.reschedule_agent.get_patient_appointments", return_value=[]):
        result = reschedule_agent(state)

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
        patch("agents.reschedule_agent.cancel_appointment") as mock_cancel,
    ):
        result = reschedule_agent(state)

    mock_cancel.assert_not_called()
    # Booking agent should have picked up and fetched slots
    assert result["requested_date"] == "2026-05-08"
    assert len(result["available_slots"]) == 1


def test_reschedule_date_stage_reserves_inline_requested_time_before_old_cancel():
    from agents.reschedule_agent import reschedule_agent

    slots = [
        {"slot_id": 10, "start_time": "08:00", "end_time": "08:30"},
        {"slot_id": 11, "start_time": "09:00", "end_time": "09:30"},
    ]
    state = _verified_state(
        current_utterance="tomorrow at 9 AM",
        existing_appointment_id=7,
        existing_appointment_details=_APPT,
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
    )

    with (
        patch("agents.booking_agent.get_llm",
              return_value=_mock_llm_response('{"date": "2026-05-08"}')),
        patch("agents.booking_agent.get_available_slots", return_value=slots),
        patch("agents.booking_agent.lock_slot", return_value=True),
        patch("agents.reschedule_agent.cancel_appointment") as mock_cancel,
    ):
        result = reschedule_agent(state)

    mock_cancel.assert_not_called()
    assert result["requested_date"] == "2026-05-08"
    assert result["locked_slot_id"] == 11
    assert result["requested_time"] == "09:00"
    assert result["booked_appointment_id"] is None
    assert "reserved the 9:00 AM slot" in result["agent_response"]


def test_reschedule_cancels_old_after_new_booking():
    from agents.reschedule_agent import reschedule_agent

    state = _verified_state(
        existing_appointment_id=7,
        existing_appointment_details=_APPT,
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-08",
        requested_time="09:00",
        booked_appointment_id=99,
        call_outcome="booked",
    )

    with patch("agents.reschedule_agent.cancel_appointment") as mock_cancel:
        result = reschedule_agent(state)

    mock_cancel.assert_called_once_with(7)
    assert result["call_outcome"] == "rescheduled"
    assert result["existing_appointment_id"] is None
    assert result["existing_appointment_details"] is None
    assert result["last_confirmed_appointment_id"] == 99
    assert result["last_confirmed_appointment_details"]["id"] == 99
    assert result["last_confirmed_appointment_details"]["doctor_name"] == "Dr. Sarah Smith"
    assert "previous" in result["agent_response"].lower()


def test_reschedule_old_cancel_error_escalates_after_new_booking():
    from agents.reschedule_agent import reschedule_agent

    state = _verified_state(
        existing_appointment_id=7,
        existing_appointment_details=_APPT,
        requested_doctor="Dr. Sarah Smith",
        requested_doctor_id=1,
        requested_date="2026-05-08",
        requested_time="09:00",
        booked_appointment_id=99,
        call_outcome="booked",
    )

    with patch("agents.reschedule_agent.cancel_appointment", side_effect=RuntimeError("db locked")):
        result = reschedule_agent(state)

    assert result["escalated"] is True
    assert result["call_outcome"] == "escalated"
    assert "new appointment is booked" in result["agent_response"].lower()


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
    assert "John Doe" not in result["call_summary"]
    assert result["escalated"] is True


def test_escalation_slack_notification_is_masked(monkeypatch):
    from agents.escalation_agent import escalation_agent

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example.invalid/test")
    state = _state(
        patient_name="John Doe",
        previous_intents=[CallIntent.BOOKING],
        requested_doctor="Dr. Sarah Smith",
        turn_count=4,
    )

    with patch("agents.escalation_agent.httpx.post") as mock_post:
        escalation_agent(state)

    mock_post.assert_called_once()
    payload = mock_post.call_args.kwargs["json"]
    assert "John Doe" not in payload["text"]
    assert "[NAME]" in payload["text"]


def test_escalation_abuse_uses_brief_response():
    from agents.escalation_agent import escalation_agent
    state = _state(guardrail_triggered="abuse")
    result = escalation_agent(state)
    assert "transfer" in result["agent_response"].lower()


# ── Guardrails (Phase 6) ──────────────────────────────────────────────────────

def test_pii_masker_masks_phone():
    from guardrails.pii_masker import mask_pii
    assert mask_pii("call me at 480-555-1234") == "call me at [PHONE]"
    assert mask_pii("+14805551234") == "[PHONE]"


def test_pii_masker_masks_dob():
    from guardrails.pii_masker import mask_pii
    assert "[DOB]" in mask_pii("born on 1990-03-05")
    assert "[DOB]" in mask_pii("date of birth: 03/05/1990")
    assert mask_pii("confirmed for 2026-05-08") == "confirmed for 2026-05-08"


def test_pii_masker_masks_email():
    from guardrails.pii_masker import mask_pii
    assert "[EMAIL]" in mask_pii("email me at john@example.com")


def test_pii_masker_masks_known_names_and_name_phrases():
    from guardrails.pii_masker import mask_pii, mask_transcript

    assert mask_pii("Patient: John Doe", names=["John Doe"]) == "Patient: [NAME]"
    assert mask_pii("my name is Jane Roe") == "my name is [NAME]"

    masked = mask_transcript(
        [{"role": "patient", "text": "John Doe, born 1990-03-05"}],
        names=["John Doe"],
    )
    assert masked == [{"role": "patient", "text": "[NAME], born [DOB]"}]


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
