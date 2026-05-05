from graph.state import CallIntent, CallState


def route_by_intent(state: CallState) -> str:
    intent = state["current_intent"]
    if intent == CallIntent.BOOKING:
        return "booking"
    if intent == CallIntent.RESCHEDULE:
        return "reschedule"
    if intent == CallIntent.CANCEL:
        return "cancel"
    if intent == CallIntent.FAQ:
        return "faq"
    if intent == CallIntent.FAREWELL:
        return "farewell"
    if intent == CallIntent.UNKNOWN:
        return "unknown"
    return "escalate"


def route_after_verification(state: CallState) -> str:
    if not state["patient_verified"]:
        if state["verification_attempts"] >= 2:
            return "escalate"
        return "need_more_info"
    # Route to the original intent
    intent = state["current_intent"]
    if intent == CallIntent.BOOKING:
        return "booking"
    if intent == CallIntent.RESCHEDULE:
        return "reschedule"
    if intent == CallIntent.CANCEL:
        return "cancel"
    return "escalate"
