import asyncio
import base64
import contextlib
import json
import os
import time

from fastapi import WebSocket

from db.call_history import end_call_record, start_call_record
from db.scheduling import release_slot
from guardrails.pii_masker import mask_pii, mask_transcript
from voice.barge_in import BargeInDetector
from voice.deepgram_stt import run_deepgram_finals
from voice.session import CallSession


def _barge_in_enabled() -> bool:
    return os.environ.get("BARGE_IN", "").strip().lower() in ("1", "true", "yes")


def _known_patient_names(session: CallSession) -> list[str]:
    if session.state and session.state.get("patient_name"):
        return [session.state["patient_name"]]
    return []


async def handle_twilio_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    print("Twilio connected")

    session = CallSession()
    deepgram_task = asyncio.create_task(
        run_deepgram_finals(session.audio_queue, session.finals_queue)
    )
    barge_in = _barge_in_enabled()
    barge_in_detector = BargeInDetector() if barge_in else None
    if barge_in_detector:
        print(
            "[barge-in] enabled "
            f"rms_threshold={barge_in_detector.threshold:g} "
            f"speech_frames={barge_in_detector.speech_frames_required} "
            f"silence_frames={barge_in_detector.silence_frames_required}"
        )

    async def handle_finals() -> None:
        while True:
            phrase = await session.finals_queue.get()
            if phrase is None:
                break
            if not phrase.strip():
                continue
            print("User: [transcript received]")
            t_turn = time.perf_counter()
            await session.cancel_speak(websocket, clear_buffer=True)
            reply = await session.process_turn(phrase)
            print(f"Agent: {mask_pii(reply, names=_known_patient_names(session))}")
            print(f"[latency] turn_total={time.perf_counter() - t_turn:.3f}s")
            session.speak_task = asyncio.create_task(session.speak(reply, websocket))
            if not barge_in:
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
                custom_params = start.get("customParameters") or {}
                session.stream_sid = start.get("streamSid") or data.get("streamSid")
                session.call_sid = start.get("callSid")
                session.caller_phone = (
                    custom_params.get("caller_phone")
                    or start.get("from")
                    or "unknown"
                )
                session.init_state()
                print(
                    f"Call started  call_sid={session.call_sid}  "
                    f"from={mask_pii(session.caller_phone)}  "
                    f"stream_sid={'set' if session.stream_sid else 'missing'}"
                )
                try:
                    start_call_record(session.call_sid, session.caller_phone)
                except Exception as exc:
                    print(f"call_history start error: {exc}")

            elif event == "media":
                audio = base64.b64decode(data["media"]["payload"])
                await session.audio_queue.put(audio)
                if (
                    barge_in_detector
                    and session.speaking
                    and barge_in_detector.is_speech(audio)
                ):
                    print("[barge-in] caller speech detected; cancelling TTS")
                    await session.cancel_speak(websocket, clear_buffer=True)
                    barge_in_detector.reset()

            elif event == "mark":
                session.handle_playback_mark(data.get("mark", {}).get("name"))

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
            if s.get("locked_slot_id") and not s.get("booked_appointment_id"):
                try:
                    release_slot(s["locked_slot_id"], session.call_sid)
                except Exception as exc:
                    print(f"slot release error: {exc}")

            names = _known_patient_names(session)
            try:
                end_call_record(
                    session.call_sid,
                    transcript=mask_transcript(s["conversation_history"], names=names),
                    intent_sequence=[i.value for i in s["previous_intents"]],
                    outcome=s.get("call_outcome"),
                    appointment_id=s.get("booked_appointment_id"),
                    patient_id=s.get("patient_id"),
                    sentiment_avg=s.get("frustration_score"),
                    escalated=s.get("escalated", False),
                    call_summary=mask_pii(s.get("call_summary"), names=names),
                )
            except Exception as exc:
                print(f"call_history end error: {exc}")

    print("Session closed")
