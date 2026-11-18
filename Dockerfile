FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend/src \
    VOICECANVAS_SHOT_DB_PATH=/app/backend/data/svg-shots.sqlite3

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/src ./src
RUN uv sync --frozen --no-dev --no-editable

RUN mkdir -p /app/backend/data

EXPOSE 8000

CMD [".venv/bin/uvicorn", "voicecanvas.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
