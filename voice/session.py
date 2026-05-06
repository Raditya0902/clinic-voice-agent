import asyncio
import contextlib
import time
from typing import Optional

from elevenlabs.core.api_error import ApiError
from fastapi import WebSocket

from voice.audio_utils import send_clear_to_caller, send_mark_to_caller, send_mulaw_to_caller
from voice.elevenlabs_tts import text_to_speech_mulaw_frames
from graph.state import CallState, initial_call_state
from graph.workflow import get_compiled_graph


class CallSession:
    def __init__(self) -> None:
        self.call_sid: Optional[str] = None
        self.stream_sid: Optional[str] = None
        self.caller_phone: Optional[str] = None
        self.audio_queue: asyncio.Queue = asyncio.Queue()
        self.finals_queue: asyncio.Queue = asyncio.Queue()
        self.speaking: bool = False
        self.speak_task: Optional[asyncio.Task] = None
        self.playback_mark_name: Optional[str] = None
        self._playback_mark_counter: int = 0
        self.state: Optional[CallState] = None

    def init_state(self) -> None:
        """Call after call_sid/stream_sid/caller_phone are populated from the start event."""
        self.state = initial_call_state(
            call_sid=self.call_sid or "",
            stream_sid=self.stream_sid or "",
            caller_phone=self.caller_phone or "",
        )

    async def process_turn(self, transcript: str) -> str:
        """
        Run one full conversation turn through LangGraph.
        Updates self.state in place. Returns the agent response text.
        """
        if self.state is None:
            self.init_state()

        self.state["current_utterance"] = transcript
        self.state["conversation_history"] = self.state["conversation_history"] + [
            {"role": "patient", "text": transcript}
        ]
        self.state["turn_count"] += 1

        t0 = time.perf_counter()
        try:
            result = await asyncio.to_thread(get_compiled_graph().invoke, self.state)
            self.state = result
            response = self.state.get("agent_response") or "I'm sorry, I didn't catch that. Could you repeat?"
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except BaseException as exc:
            print(f"LangGraph error: {type(exc).__name__}: {exc}")
            response = "I'm having a technical issue. Please call (480) 555-0100 for assistance."
        finally:
            print(f"[latency] langgraph={time.perf_counter() - t0:.3f}s")

        self.state["conversation_history"] = self.state["conversation_history"] + [
            {"role": "agent", "text": response}
        ]
        return response

    def _next_playback_mark_name(self) -> str:
        self._playback_mark_counter += 1
        return f"tts-{self._playback_mark_counter}"

    def handle_playback_mark(self, mark_name: str | None) -> None:
        """Mark outbound TTS playback complete when Twilio finishes its buffer."""
        if mark_name and mark_name == self.playback_mark_name:
            self.playback_mark_name = None
            self.speaking = False

    async def speak(self, text: str, websocket: WebSocket) -> None:
        """Stream TTS audio to the caller. Designed to run as a cancellable asyncio Task."""
        if not self.stream_sid:
            print("[tts] skipped — missing Twilio stream SID")
            return
        self.speaking = True
        t0 = time.perf_counter()
        first_frame = True
        sent_frames = 0
        cancelled = False
        mark_sent = False
        try:
            async for frame in text_to_speech_mulaw_frames(text):
                if first_frame:
                    print(f"[latency] tts_first_frame={time.perf_counter() - t0:.3f}s")
                    first_frame = False
                await send_mulaw_to_caller(websocket, self.stream_sid, frame)
                sent_frames += 1
            if sent_frames:
                mark_name = self._next_playback_mark_name()
                self.playback_mark_name = mark_name
                await send_mark_to_caller(websocket, self.stream_sid, mark_name)
                mark_sent = True
        except ApiError as exc:
            if exc.status_code == 402:
                print("ElevenLabs 402: upgrade plan or use a voice from your account.")
            else:
                print(f"[tts] ElevenLabs API error ({exc.status_code}): {exc.body}")
        except asyncio.CancelledError:
            cancelled = True
            print("[tts] cancelled")
            raise
        except Exception as exc:
            print(f"[tts] error — {type(exc).__name__}: {exc}")
        finally:
            if sent_frames == 0 and not cancelled:
                print("[tts] no audio frames sent")
            if cancelled or not sent_frames or not mark_sent:
                self.playback_mark_name = None
                self.speaking = False

    async def cancel_speak(
        self,
        websocket: WebSocket | None = None,
        *,
        clear_buffer: bool = False,
    ) -> None:
        """Cancel in-flight TTS if any (barge-in or turn change)."""
        task_running = bool(self.speak_task and not self.speak_task.done())
        was_playing = self.speaking or task_running or bool(self.playback_mark_name)

        if task_running:
            self.speak_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.speak_task

        if clear_buffer and websocket and self.stream_sid and was_playing:
            try:
                await send_clear_to_caller(websocket, self.stream_sid)
            except Exception as exc:
                print(f"[tts] clear failed — {type(exc).__name__}: {exc}")

        if was_playing:
            self.playback_mark_name = None
            self.speaking = False
