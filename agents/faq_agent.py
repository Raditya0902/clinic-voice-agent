from graph.llm import get_llm
from graph.state import CallState
from rag.vectorstore import format_context, query as rag_query

_SYSTEM_TEMPLATE = """\
You are a friendly receptionist for Sunrise Health Clinic answering a phone call.
Answer the patient's question using ONLY the clinic information provided below.
Keep your response to 2-3 sentences — this is a phone call, not an email.
Do not mention you are an AI. Speak naturally and warmly.
If the answer is not in the provided information, say:
"I don't have that detail on hand, but our front desk at (480) 555-0100 can help you."

--- CLINIC INFORMATION ---
{context}"""


def faq_agent(state: CallState) -> CallState:
    query = state["current_utterance"]

    chunks = rag_query(query, top_k=3)
    context = format_context(chunks) if chunks else "No relevant information found."

    messages = [
        {"role": "system", "content": _SYSTEM_TEMPLATE.format(context=context)},
        {"role": "user", "content": query},
    ]

    try:
        response = get_llm().invoke(messages)
        answer = response.content.strip()
    except Exception as exc:
        print(f"FAQ agent LLM error: {exc}")
        answer = "I'm having trouble looking that up right now. Please call our front desk at (480) 555-0100 for assistance."

    state["faq_query"] = query
    state["faq_answer"] = answer
    state["agent_response"] = answer
    return state
