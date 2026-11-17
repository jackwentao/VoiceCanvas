FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend/src \
    VOICECANVAS_PROJECT_DB_PATH=/app/backend/data/voicecanvas.sqlite3

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

COPY backend/src ./src
COPY backend/scripts ./scripts

RUN mkdir -p /app/backend/data

EXPOSE 8000

CMD ["uv", "run", "--frozen", "--no-dev", "--no-editable", "uvicorn", "voicecanvas.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
