"""持久化 Agent 任务，并在数据库中阻止同项目的重复执行。"""

import sqlite3
from pathlib import Path

from voicecanvas.application.shot_service import ShotConflict
from voicecanvas.domain.storyboard_agent import StoryboardAgentRun
from voicecanvas.infrastructure.sqlite_storyboard_repository import SQLiteStoryboardRepository


class SQLiteAgentRunRepository(SQLiteStoryboardRepository):
    def __init__(self, path: Path):
        super().__init__(path)
        with self._connect() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS svg_agent_runs "
                "(id TEXT PRIMARY KEY, board_id TEXT NOT NULL, status TEXT NOT NULL, payload TEXT)"
            )
            c.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS svg_agent_active "
                "ON svg_agent_runs(board_id) WHERE status='running'"
            )

    def latest(self, board_id: str) -> StoryboardAgentRun | None:
        with self._connect() as c:
            row = c.execute(
                "SELECT payload FROM svg_agent_runs WHERE board_id=? ORDER BY rowid DESC LIMIT 1",
                (board_id,),
            ).fetchone()
        return StoryboardAgentRun.model_validate_json(row[0]) if row else None

    def get_run(self, run_id: str) -> StoryboardAgentRun:
        with self._connect() as c:
            row = c.execute("SELECT payload FROM svg_agent_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise ValueError("任务不存在")
        return StoryboardAgentRun.model_validate_json(row[0])

    def create_run(self, run: StoryboardAgentRun, expected_version: int) -> None:
        try:
            with self._connect() as c:
                c.execute("BEGIN IMMEDIATE")
                row = c.execute(
                    "SELECT version FROM svg_storyboards WHERE id=?", (run.board_id,)
                ).fetchone()
                if not row or row[0] != expected_version:
                    raise ShotConflict("分镜已变化，请刷新后重新提交")
                c.execute(
                    "INSERT INTO svg_agent_runs VALUES (?,?,?,?)",
                    (run.id, run.board_id, run.status, run.model_dump_json(by_alias=True)),
                )
        except sqlite3.IntegrityError as error:
            raise ShotConflict("当前分镜已有执行中的任务，请等待或刷新查看") from error

    def save_run(self, run: StoryboardAgentRun) -> None:
        with self._connect() as c:
            c.execute(
                "UPDATE svg_agent_runs SET status=?,payload=? WHERE id=?",
                (run.status, run.model_dump_json(by_alias=True), run.id),
            )
