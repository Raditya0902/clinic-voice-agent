import asyncio
import os

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types.listen_v1results import ListenV1Results


async def run_deepgram_finals(audio_queue: asyncio.Queue, finals_queue: asyncio.Queue) -> None:
    """Stream mulaw chunks to Deepgram; push each finalized transcript to finals_queue."""
    api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPGRAM_API_KEY not set in .env")

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
