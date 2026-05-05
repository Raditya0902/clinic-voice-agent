import re

_PHONE_RE = re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b')
_DOB_RE = re.compile(r'\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b')
_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')


def mask_pii(text: str) -> str:
    """Replace phone numbers, dates of birth, and emails with placeholders."""
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _DOB_RE.sub("[DOB]", text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    return text


def mask_transcript(turns: list[dict]) -> list[dict]:
    """Return a copy of the conversation history with PII masked."""
    return [{"role": t["role"], "text": mask_pii(t["text"])} for t in turns]
