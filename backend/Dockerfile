FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-liberation fonts-dejavu fonts-noto-core libgl1 libglib2.0-0 ca-certificates nodejs && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend /app/backend
RUN useradd --create-home studio && mkdir -p /data && chown studio:studio /data
USER studio
CMD ["python", "backend/server.py"]
