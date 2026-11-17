"""分镜元数据与新增镜头在同一 SQLite 事务提交，不物理删除画面。"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from voicecanvas.application.shot_service import ShotConflict
from voicecanvas.domain.shot import ShotDocument
from voicecanvas.domain.storyboard import Storyboard
from voicecanvas.infrastructure.sqlite_shot_repository import SQLiteShotRepository


class SQLiteStoryboardRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        SQLiteShotRepository(db_path)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS svg_storyboards (id TEXT PRIMARY KEY, "
                "version INTEGER NOT NULL, payload TEXT NOT NULL, "
                "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _insert_shots(connection, shots: list[ShotDocument]):
        for shot in shots:
            connection.execute(
                "INSERT INTO svg_shots VALUES (?, ?, ?)",
                (shot.id, shot.version, shot.model_dump_json(by_alias=True)),
            )

    def create(self, board: Storyboard, shots: list[ShotDocument]):
        with self._connect() as connection:
            self._insert_shots(connection, shots)
            connection.execute(
                "INSERT INTO svg_storyboards (id,version,payload) VALUES (?,?,?)",
                (board.id, board.version, board.model_dump_json(by_alias=True)),
            )

    def load(self, board_id: str) -> Storyboard | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM svg_storyboards WHERE id=?", (board_id,)
            ).fetchone()
        return Storyboard.model_validate_json(row[0]) if row else None

    def list_recent(self) -> list[Storyboard]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM svg_storyboards ORDER BY updated_at DESC, rowid DESC LIMIT 50"
            ).fetchall()
        return [Storyboard.model_validate_json(row[0]) for row in rows]

    def load_shots(self, ids: list[str]) -> dict[str, ShotDocument]:
        if not ids:
            return {}
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT id,payload FROM svg_shots WHERE id IN ({','.join('?' for _ in ids)})", ids
            ).fetchall()
        return {row[0]: ShotDocument.model_validate_json(row[1]) for row in rows}

    def save(self, board: Storyboard, expected_version: int, shots: list[ShotDocument]):
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE svg_storyboards SET version=?,payload=?,updated_at=CURRENT_TIMESTAMP "
                "WHERE id=? AND version=?",
                (board.version, board.model_dump_json(by_alias=True), board.id, expected_version),
            ).rowcount
            if changed != 1:
                raise ShotConflict("分镜已在其他页面修改，请重新操作")
            self._insert_shots(connection, shots)
