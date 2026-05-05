import json

from db.patients import lookup_patient
from graph.llm import get_llm
from graph.state import CallState

_EXTRACT_PROMPT = """\
Extract the patient's full name and date of birth from the conversation below.
The patient may have given their name in one message and DOB in another — look across all messages.
Return JSON only — no prose, no markdown:
{"name": "John Doe", "dob": "1990-03-05"}
Use null for any field not found anywhere in the conversation.
Convert spoken or written dates to YYYY-MM-DD.
Examples: "March 5th 1990" -> "1990-03-05", "07/22/1985" -> "1985-07-22"."""


def _extract_name_dob(
    utterance: str, history: list[dict]
) -> tuple[str | None, str | None]:
    # Include last 6 patient turns so the LLM can piece together name+DOB across turns
    context_turns = [
        t for t in history[-8:] if t["role"] == "patient"
    ]
    context = "\n".join(t["text"] for t in context_turns)
    if utterance not in context:
        context = context + "\n" + utterance

    messages = [
        {"role": "system", "content": _EXTRACT_PROMPT},
        {"role": "user", "content": context},
    ]
    try:
        resp = get_llm().invoke(messages)
        data = json.loads(resp.content.strip())
        return data.get("name"), data.get("dob")
    except Exception:
        return None, None


def verification_agent(state: CallState) -> CallState:
    utterance = state["current_utterance"]
    name, dob = _extract_name_dob(utterance, state["conversation_history"])

    if name and dob:
        patient = lookup_patient(full_name=name, date_of_birth=dob)
        if patient:
            state["patient_verified"] = True
            state["patient_id"] = patient["id"]
            state["patient_name"] = f"{patient['first_name']} {patient['last_name']}"
            # Leave agent_response empty — booking_agent will greet the patient
            # and ask the first booking question in the same turn.
            state["agent_response"] = ""
            return state

        # Name+DOB extracted but no DB match
        state["verification_attempts"] = state["verification_attempts"] + 1
        state["agent_response"] = (
            "I'm sorry, I couldn't find your records with that information. "
            "Could you please confirm your full name and date of birth?"
        )
        return state

    # Could not extract both — ask specifically for what's missing
    if name and not dob:
        state["agent_response"] = "Got it. And could you tell me your date of birth?"
    elif dob and not name:
        state["agent_response"] = "Got it. And could you tell me your full name?"
    else:
        state["agent_response"] = (
            "I need to verify your identity before we proceed. "
            "Could you please tell me your full name and date of birth?"
        )
    return state
