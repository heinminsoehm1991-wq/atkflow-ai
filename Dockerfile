FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "yt-dlp[default,curl-cffi]"

WORKDIR /app
COPY server.py .
ENV PYTHONUNBUFFERED=1
CMD ["python", "server.py"]
