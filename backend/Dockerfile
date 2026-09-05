# Backend image, sized for Hugging Face Spaces' free CPU tier
# (2 vCPU / 16GB RAM). Kokoro needs PyTorch, so this is a normal container
# rather than a serverless function.

FROM python:3.12-slim

# espeak-ng is not optional: Kokoro needs it for grapheme-to-phoneme
# conversion, and the copy bundled with espeakng-loader has a build-machine
# path compiled into it. FFmpeg does all the audio assembly.
RUN apt-get update && apt-get install -y --no-install-recommends \
        espeak-ng \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Spaces run containers as uid 1000 and only that user may write.
RUN useradd -m -u 1000 app
USER app
ENV PATH="/home/app/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/home/app/.cache/huggingface

WORKDIR /home/app/api

COPY --chown=app:app requirements.in ./
RUN pip install --no-cache-dir --user -r requirements.in

COPY --chown=app:app . .

# Fetch the voice model at build time. Left to first request it would add
# several seconds and depend on the Hub being reachable right then.
RUN python -c "\
from app.config import get_settings; get_settings().apply_espeak_env();\
from kokoro import KPipeline; KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M');\
print('model cached')"

# Spaces routes to 7860 by default.
ENV PORT=7860
EXPOSE 7860

# One worker on purpose: the model is held in memory, and a second copy would
# double roughly 1GB for no gain on two cores.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
