import re
from collections.abc import Iterable

_PHONE_RE = re.compile(r'(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)')
_DATE_VALUE_RE = r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b'
_DOB_CONTEXT_RE = re.compile(
    rf'\b(born(?:\s+on)?|date\s+of\s+birth|dob|d\.o\.b\.|birthday)'
    rf'(\s*(?:is|:)?\s*)({_DATE_VALUE_RE})',
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
_NAME_PHRASE_RE = re.compile(
    r'\b(full name is|my name is|name is|patient:)\s+'
    r"([A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*){0,3})",
    re.IGNORECASE,
)


def _known_name_fragments(names: Iterable[str] | None) -> list[str]:
    fragments: set[str] = set()
    for raw_name in names or []:
        name = raw_name.strip()
        if not name:
            continue
        fragments.add(name)
        for part in name.split():
            if len(part) > 2:
                fragments.add(part)
    return sorted(fragments, key=len, reverse=True)


def _mask_known_names(text: str, names: Iterable[str] | None) -> str:
    for name in _known_name_fragments(names):
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", re.IGNORECASE)
        text = pattern.sub("[NAME]", text)
    return text


def _mask_name_phrase(match: re.Match) -> str:
    return f"{match.group(1)} [NAME]"


def _mask_dob_context(match: re.Match) -> str:
    return f"{match.group(1)}{match.group(2)}[DOB]"


def mask_pii(text: str | None, names: Iterable[str] | None = None) -> str:
    """Replace phone numbers, DOBs, emails, and known patient names with placeholders."""
    if text is None:
        return ""
    text = str(text)
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _DOB_CONTEXT_RE.sub(_mask_dob_context, text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _mask_known_names(text, names)
    text = _NAME_PHRASE_RE.sub(_mask_name_phrase, text)
    return text


def mask_transcript(turns: list[dict], names: Iterable[str] | None = None) -> list[dict]:
    """Return a copy of the conversation history with PII masked."""
    return [{"role": t["role"], "text": mask_pii(t["text"], names=names)} for t in turns]
