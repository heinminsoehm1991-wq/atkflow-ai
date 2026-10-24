FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade --pre "yt-dlp[default,curl-cffi]" edge-tts

WORKDIR /app
COPY server.py render_jobs.py prepare_transcript.py ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "server.py"]

