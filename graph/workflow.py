from langgraph.graph import StateGraph, END

from graph.state import CallState
from graph.router import route_by_intent, route_after_verification

from agents.sentiment_agent import sentiment_agent
from agents.intent_agent import intent_agent
from agents.verification_agent import verification_agent
from agents.booking_agent import booking_agent
from agents.reschedule_agent import reschedule_agent
from agents.cancellation_agent import cancellation_agent
from agents.faq_agent import faq_agent
from agents.escalation_agent import escalation_agent
from agents.farewell_agent import farewell_agent

_compiled_graph = None


def build_workflow():
    workflow = StateGraph(CallState)

    workflow.add_node("sentiment", sentiment_agent)
    workflow.add_node("intent", intent_agent)
    workflow.add_node("verification", verification_agent)
    workflow.add_node("booking", booking_agent)
    workflow.add_node("reschedule", reschedule_agent)
    workflow.add_node("cancellation", cancellation_agent)
    workflow.add_node("faq", faq_agent)
    workflow.add_node("escalation", escalation_agent)
    workflow.add_node("farewell", farewell_agent)

    # Sentiment → intent on every turn
    workflow.set_entry_point("sentiment")
    workflow.add_edge("sentiment", "intent")

    # Intent routes to specialist (or verification gate)
    workflow.add_conditional_edges(
        "intent",
        route_by_intent,
        {
            "booking": "verification",
            "reschedule": "verification",
            "cancel": "verification",
            "faq": "faq",
            "escalate": "escalation",
            "farewell": "farewell",
            "unknown": END,
        },
    )

    # Verification gates booking/reschedule/cancel
    workflow.add_conditional_edges(
        "verification",
        route_after_verification,
        {
            "booking": "booking",
            "reschedule": "reschedule",
            "cancel": "cancellation",
            "escalate": "escalation",
            "need_more_info": END,
        },
    )

    workflow.add_edge("booking", END)
    workflow.add_edge("reschedule", END)
    workflow.add_edge("cancellation", END)
    workflow.add_edge("faq", END)
    workflow.add_edge("escalation", END)
    workflow.add_edge("farewell", END)

    return workflow.compile()


def get_compiled_graph():
    """Build and cache the graph on first call."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_workflow()
    return _compiled_graph
