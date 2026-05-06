OUTCOME_COLORS = {
    "booked": "🟢",
    "rescheduled": "🟣",
    "cancelled": "🔵",
    "escalated": "🔴",
    "faq_answered": "🟡",
    "completed": "⚪",
    None: "⚪",
}

STATUS_LABEL = {
    "booked": "Booked",
    "rescheduled": "Rescheduled",
    "cancelled": "Cancelled",
    "escalated": "Escalated",
    "faq_answered": "FAQ Answered",
    "completed": "Completed",
    None: "Incomplete",
}


def label_for_outcome(outcome: str | None, default: str = "Unknown") -> str:
    return STATUS_LABEL.get(outcome, default)


def format_status(outcome: str | None, *, active: bool = False) -> str:
    if active:
        return "🔴 Active"
    return f"{OUTCOME_COLORS.get(outcome, '⚪')} {label_for_outcome(outcome)}"
