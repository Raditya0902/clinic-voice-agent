_CLINIC_KEYWORDS = {
    "appointment", "schedule", "book", "cancel", "reschedule",
    "doctor", "physician", "specialist", "hours", "open", "close",
    "insurance", "coverage", "copay", "deductible",
    "location", "address", "parking", "directions",
    "service", "procedure", "exam", "checkup", "visit",
    "patient", "record", "prescription", "referral",
    "clinic", "office", "staff",
}


def is_in_scope(utterance: str) -> bool:
    """Return True if the utterance is related to clinic operations."""
    text = utterance.lower()
    return any(kw in text for kw in _CLINIC_KEYWORDS)
