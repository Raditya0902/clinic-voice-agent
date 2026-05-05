_ABUSE_TERMS = {
    "idiot", "stupid", "moron", "dumb", "incompetent",
    "damn", "crap", "screw you", "shut up",
    "pathetic", "garbage", "trash",
}


def is_abusive(utterance: str) -> bool:
    """Return True if the utterance contains abusive language."""
    text = utterance.lower()
    return any(term in text for term in _ABUSE_TERMS)
