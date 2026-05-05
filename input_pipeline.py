# input_pipeline.py — alternate entry point (same app as full_pipeline.py).
import uvicorn

from full_pipeline import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
