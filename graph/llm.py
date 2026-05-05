import os

from langchain_groq import ChatGroq

_llm: ChatGroq | None = None


def get_llm() -> ChatGroq:
    """Return a shared ChatGroq instance (lazy singleton)."""
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model=os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"),
            api_key=os.environ.get("GROQ_API_KEY"),
            temperature=0.3,
            max_tokens=200,  # short responses — this is voice, not text
        )
    return _llm
