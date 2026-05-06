from __future__ import annotations

from enum import Enum
from datetime import datetime, timezone
from typing import Literal, Optional
from typing_extensions import TypedDict


class CallIntent(str, Enum):
    BOOKING = "booking"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    FAQ = "faq"
    ESCALATE = "escalate"
    FAREWELL = "farewell"
    UNKNOWN = "unknown"


class CallState(TypedDict):
    # Session identifiers
    call_sid: str
    stream_sid: str
    caller_phone: str

    # Conversation
    conversation_history: list[dict]   # [{"role": "patient"|"agent", "text": "..."}]
    current_utterance: str
    agent_response: str

    # Intent routing
    current_intent: CallIntent
    intent_confidence: float
    previous_intents: list[CallIntent]

    # Patient verification
    patient_verified: bool
    patient_id: Optional[int]
    patient_name: Optional[str]
    verification_attempts: int

    # Booking slot-filling
    active_appointment_workflow: Optional[Literal["booking", "reschedule", "cancel"]]
    requested_doctor: Optional[str]
    requested_doctor_id: Optional[int]
    requested_date: Optional[str]
    requested_time: Optional[str]
    reason_for_visit: Optional[str]
    available_slots: list[dict]
    locked_slot_id: Optional[int]
    booked_appointment_id: Optional[int]
    last_confirmed_appointment_id: Optional[int]
    last_confirmed_appointment_details: Optional[dict]

    # Reschedule / cancel
    existing_appointment_id: Optional[int]
    existing_appointment_details: Optional[dict]

    # FAQ
    faq_query: Optional[str]
    faq_answer: Optional[str]

    # Sentiment and safety
    frustration_score: float
    guardrail_triggered: Optional[str]

    # Call metadata
    call_start_time: str
    turn_count: int
    total_latency_ms: float
    total_tokens_used: int
    escalated: bool
    call_outcome: Optional[str]
    call_summary: Optional[str]


def initial_call_state(
    call_sid: str,
    stream_sid: str,
    caller_phone: str,
) -> CallState:
    return CallState(
        call_sid=call_sid,
        stream_sid=stream_sid,
        caller_phone=caller_phone,
        conversation_history=[],
        current_utterance="",
        agent_response="",
        current_intent=CallIntent.UNKNOWN,
        intent_confidence=0.0,
        previous_intents=[],
        patient_verified=False,
        patient_id=None,
        patient_name=None,
        verification_attempts=0,
        active_appointment_workflow=None,
        requested_doctor=None,
        requested_doctor_id=None,
        requested_date=None,
        requested_time=None,
        reason_for_visit=None,
        available_slots=[],
        locked_slot_id=None,
        booked_appointment_id=None,
        last_confirmed_appointment_id=None,
        last_confirmed_appointment_details=None,
        existing_appointment_id=None,
        existing_appointment_details=None,
        faq_query=None,
        faq_answer=None,
        frustration_score=0.0,
        guardrail_triggered=None,
        call_start_time=datetime.now(timezone.utc).isoformat(),
        turn_count=0,
        total_latency_ms=0.0,
        total_tokens_used=0,
        escalated=False,
        call_outcome=None,
        call_summary=None,
    )
