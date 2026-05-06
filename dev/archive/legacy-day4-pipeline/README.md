# Legacy Day 4 Pipeline Scripts

This directory preserves the original Day 4 prototype scripts:

- `full_pipeline.py`
- `deepgram_feed.py`
- `elevenlabs_stream.py`
- `input_pipeline.py`

They are superseded by the maintained modular voice server in `voice/`.

The current runtime entry point is:

```bash
uvicorn voice.server:app --host 0.0.0.0 --port 8000 --reload
```

These scripts are kept for learning and reference only. Do not use them for the final demo path.
