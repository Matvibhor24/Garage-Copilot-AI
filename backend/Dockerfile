# GarageCopilot backend for Cloud Run. Build from backend/: docker build -t garage-copilot .
# mirror.gcr.io is Google's Docker Hub mirror (no Hub rate limits in Cloud Build)
FROM mirror.gcr.io/library/python:3.12-slim

RUN pip install --no-cache-dir "uv==0.11.*"
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
# Manual catalog and the team's procedure sheets (the manufacturer PDFs are never in the image: they are read
# from gs://<bucket>/manuals/ by the manuals-ingest job)
COPY manuals/catalog.json ./manuals/catalog.json
COPY manuals/procedures ./manuals/procedures

# Cloud Run sets PORT. One worker: scale with instances, not processes.
# The manuals-ingest Cloud Run Job runs this same image with: python -m app.manuals_ingest
ENV PATH="/app/.venv/bin:$PATH"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
