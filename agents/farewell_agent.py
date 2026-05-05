from graph.state import CallState


def farewell_agent(state: CallState) -> CallState:
    state["agent_response"] = (
        "Goodbye! Have a wonderful day. "
        "We look forward to seeing you at Sunrise Health Clinic."
    )
    if not state.get("call_outcome"):
        state["call_outcome"] = "completed"
    return state
