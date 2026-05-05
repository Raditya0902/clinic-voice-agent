import asyncio
import base64
import contextlib
import json
import os
import time

from fastapi import WebSocket

from db.call_history import end_call_record, start_call_record
from guardrails.pii_masker import mask_transcript
from voice.deepgram_stt import run_deepgram_finals
from voice.session import CallSession


def _barge_in_enabled() -> bool:
    return os.environ.get("BARGE_IN", "").strip().lower() in ("1", "true", "yes")


async def handle_twilio_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    print("Twilio connected")

    session = CallSession()
    deepgram_task = asyncio.create_task(
        run_deepgram_finals(session.audio_queue, session.finals_queue)
    )
    barge_in = _barge_in_enabled()

    async def handle_finals() -> None:
        while True:
            phrase = await session.finals_queue.get()
            if phrase is None:
                break
            if not phrase.strip():
                continue
            print(f"User: {phrase}")
            t_turn = time.perf_counter()
            await session.cancel_speak()
            reply = await session.process_turn(phrase)
            print(f"Agent: {reply}")
            print(f"[latency] turn_total={time.perf_counter() - t_turn:.3f}s")
            session.speak_task = asyncio.create_task(session.speak(reply, websocket))
            try:
                await session.speak_task
            except asyncio.CancelledError:
                pass

    responder = asyncio.create_task(handle_finals())

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                start = data.get("start", {})
                session.stream_sid = start.get("streamSid")
                session.call_sid = start.get("callSid")
                session.caller_phone = start.get("from", "unknown")
                session.init_state()
                print(f"Call started  call_sid={session.call_sid}  from={session.caller_phone}")
                try:
                    start_call_record(session.call_sid, session.caller_phone)
                except Exception as exc:
                    print(f"call_history start error: {exc}")

            elif event == "media":
                audio = base64.b64decode(data["media"]["payload"])
                await session.audio_queue.put(audio)
                if barge_in and session.speaking:
                    await session.cancel_speak()

            elif event == "stop":
                print("Call ended (stop event)")
                break

    except Exception as exc:
        print(f"Stream error: {exc}")
    finally:
        await session.audio_queue.put(None)
        try:
            await deepgram_task
        except Exception as exc:
            print(f"Deepgram cleanup: {exc}")
        await session.finals_queue.put(None)
        responder.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await responder
        await session.cancel_speak()

        # Store call record on session close
        if session.call_sid and session.state:
            s = session.state
            try:
                end_call_record(
                    session.call_sid,
                    transcript=mask_transcript(s["conversation_history"]),
                    intent_sequence=[i.value for i in s["previous_intents"]],
                    outcome=s.get("call_outcome"),
                    appointment_id=s.get("booked_appointment_id"),
                    patient_id=s.get("patient_id"),
                    sentiment_avg=s.get("frustration_score"),
                    escalated=s.get("escalated", False),
                    call_summary=s.get("call_summary"),
                )
            except Exception as exc:
                print(f"call_history end error: {exc}")

    print("Session closed")
