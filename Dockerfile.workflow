FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-workflows.txt ./
RUN pip install --no-cache-dir -r requirements-workflows.txt
COPY render_jobs.py workflow.py ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "workflow.py"]
