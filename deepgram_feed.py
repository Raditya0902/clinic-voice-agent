# deepgram_feed.py — stream inbound audio to Deepgram; enqueue finalized phrases.
import asyncio
import os
from pathlib import Path

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types.listen_v1results import ListenV1Results


def _load_env_files() -> None:
    for path in (
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / "day3" / ".env",
    ):
        if not path.is_file():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"\''))
            else:
                os.environ.setdefault("DEEPGRAM_API_KEY", line)


_load_env_files()


async def run_deepgram_finals(audio_queue, finals_queue) -> None:
    """Forward mulaw chunks to Deepgram; push each *final* transcript chunk to finals_queue."""
    api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Set DEEPGRAM_API_KEY in day4/.env or day3/.env")

    client = AsyncDeepgramClient(api_key=api_key)

    async def on_message(message: object) -> None:
        if not isinstance(message, ListenV1Results):
            return
        if not (message.is_final or message.speech_final):
            return
        ch = message.channel
        if not ch or not ch.alternatives:
            return
        sentence = ch.alternatives[0].transcript.strip()
        if sentence:
            print(f"Deepgram (final): '{sentence}'")
            await finals_queue.put(sentence)

    def on_error(error: object) -> None:
        print(f"Deepgram error: {error}")

    async with client.listen.v1.connect(
        model="nova-2",
        language="en-US",
        encoding="mulaw",
        sample_rate=8000,
        channels=1,
        endpointing=300,
        interim_results="true",
    ) as connection:
        connection.on(EventType.MESSAGE, on_message)
        connection.on(EventType.ERROR, on_error)
        listen_task = asyncio.create_task(connection.start_listening())
        try:
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                await connection.send_media(chunk)
            await connection.send_finalize()
            await asyncio.sleep(1.0)
        finally:
            listen_task.cancel()
            try:
                await listen_task
            except asyncio.CancelledError:
                pass
