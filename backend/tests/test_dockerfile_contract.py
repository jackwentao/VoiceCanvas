from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def test_dockerfile_keeps_backend_runtime_inputs() -> None:
    dockerfile = (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")

    assert "uv sync --frozen --no-dev --no-editable" in dockerfile
    assert "backend/src ./src" in dockerfile
    assert "backend/scripts ./scripts" in dockerfile
    assert "frontend/src/prototype/render-catalog.json" in dockerfile
    assert "VOICECANVAS_PROJECT_DB_PATH=/app/backend/data/voicecanvas.sqlite3" in dockerfile
    assert 'uvicorn", "voicecanvas.api.main:app"' in dockerfile


def test_dockerignore_excludes_local_runtime_state() -> None:
    dockerignore = (ROOT_DIR / ".dockerignore").read_text(encoding="utf-8")

    assert "backend/.venv" in dockerignore
    assert "backend/data" in dockerignore
    assert "backend/artifacts" in dockerignore
    assert "frontend/node_modules" in dockerignore
    assert "backend/.env" in dockerignore
