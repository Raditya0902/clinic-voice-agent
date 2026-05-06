from pathlib import Path
import os
import re

from graph.llm import get_llm
from graph.state import CallState
from rag.vectorstore import format_context, query as rag_query

KNOWLEDGE_DIR = Path(__file__).parent.parent / "rag" / "clinic_knowledge"
FAQ_RETRIEVAL_MODE_ENV = "FAQ_RETRIEVAL_MODE"
FRONT_DESK_FALLBACK = (
    "I don't have that detail on hand, but our front desk at (480) 555-0100 can help you."
)

_SYSTEM_TEMPLATE = """\
You are a friendly receptionist for Sunrise Health Clinic answering a phone call.
Answer the patient's question using ONLY the clinic information provided below.
Keep your response to 1-2 short phone-friendly sentences.
Do not mention you are an AI. Speak naturally and warmly.
If the answer is not in the provided information, say only:
"{fallback}"

--- CLINIC INFORMATION ---
{context}"""


def _markdown_fallback_context(query: str, top_k: int = 3) -> str:
    query_terms = {
        term for term in re.findall(r"[a-z0-9]+", query.lower())
        if len(term) > 2
    }
    scored: list[tuple[int, str]] = []

    for md_file in sorted(KNOWLEDGE_DIR.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for chunk in (c.strip() for c in content.split("\n\n") if len(c.strip()) >= 20):
            chunk_terms = set(re.findall(r"[a-z0-9]+", chunk.lower()))
            score = len(query_terms & chunk_terms)
            if score > 0:
                scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return "No relevant information found."
    return "\n\n".join(chunk for _, chunk in scored[:top_k])


def _safe_rag_context(query: str) -> str:
    mode = os.environ.get(FAQ_RETRIEVAL_MODE_ENV, "markdown").strip().lower()
    if mode != "chroma":
        return _markdown_fallback_context(query)

    try:
        chunks = rag_query(query, top_k=3)
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except BaseException as exc:
        print(f"FAQ RAG error: {type(exc).__name__}: {exc}")
        return _markdown_fallback_context(query)

    return format_context(chunks) if chunks else "No relevant information found."


def faq_agent(state: CallState) -> CallState:
    query = state["current_utterance"]
    context = _safe_rag_context(query)

    if context == "No relevant information found.":
        answer = FRONT_DESK_FALLBACK
    else:
        messages = [
            {
                "role": "system",
                "content": _SYSTEM_TEMPLATE.format(
                    context=context,
                    fallback=FRONT_DESK_FALLBACK,
                ),
            },
            {"role": "user", "content": query},
        ]

        try:
            response = get_llm().invoke(messages)
            answer = response.content.strip()
        except Exception as exc:
            print(f"FAQ agent LLM error: {exc}")
            answer = FRONT_DESK_FALLBACK

    state["faq_query"] = query
    state["faq_answer"] = answer
    state["agent_response"] = answer
    if state.get("call_outcome") is None:
        state["call_outcome"] = "faq_answered"
    return state
