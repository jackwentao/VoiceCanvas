import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from voicecanvas.application.project_repository import ProjectRepository
from voicecanvas.domain.project import Project, Scene


class SQLiteProjectRepository(ProjectRepository):
    """基于 SQLite 的项目状态仓储，用于比赛演示阶段的稳定本地持久化。"""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def get_or_create(self, project_id: str) -> Project:
        project = self.load(project_id)
        if project is None:
            project = self.create_demo_project(project_id)
            self.save(project)
        return project

    def load(self, project_id: str) -> Project | None:
        with self._connect() as connection:
            row = connection.execute(
                "select payload from projects where id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return Project.model_validate_json(row[0])

    def save(self, project: Project) -> None:
        payload = json.dumps(project.model_dump(by_alias=True), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                insert into projects (id, payload, updated_at)
                values (?, ?, ?)
                on conflict(id) do update set
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (project.id, payload, self._now()),
            )

    def list(self) -> list[Project]:
        with self._connect() as connection:
            rows = connection.execute(
                "select payload from projects order by updated_at desc, id asc"
            ).fetchall()
        return [Project.model_validate_json(row[0]) for row in rows]

    def create_blank_project(
        self,
        title: str = "未命名项目",
        mode: Literal["free_canvas", "storyboard"] = "storyboard",
        project_id: str | None = None,
    ) -> Project:
        resolved_project_id = project_id or self._next_project_id()
        return Project(
            id=resolved_project_id,
            title=title.strip() or "未命名项目",
            mode=mode,
            scenes=[Scene(id="scene_1", name="空白画布", order=1)],
            activeSceneId="scene_1",
        )

    def create_demo_project(self, project_id: str) -> Project:
        return Project(
            id=project_id,
            title="VoiceCanvas Demo",
            mode="storyboard",
            scenes=[Scene(id="scene_1", name="空白画布", order=1)],
            activeSceneId="scene_1",
        )

    def save_runtime(self, project_id: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "insert into workspace_runtime (project_id, payload) values (?, ?) "
                "on conflict(project_id) do update set payload=excluded.payload",
                (project_id, json.dumps(payload, ensure_ascii=False)),
            )

    def load_runtime(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "select payload from workspace_runtime where project_id = ?", (project_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists projects (
                    id text primary key,
                    payload text not null,
                    updated_at text not null
                )
                """
            )

            connection.execute(
                "create table if not exists workspace_runtime "
                "(project_id text primary key, payload text not null)"
            )

    def _next_project_id(self) -> str:
        while True:
            project_id = f"project_{uuid4().hex[:12]}"
            if self.load(project_id) is None:
                return project_id

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
