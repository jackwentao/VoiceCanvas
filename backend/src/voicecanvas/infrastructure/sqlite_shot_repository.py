"""SQLite 单镜头仓储，与旧 Project 表独立，使用版本号防止并发覆盖。"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from voicecanvas.application.shot_service import ShotConflict
from voicecanvas.domain.shot import ShotDocument


class SQLiteShotRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS svg_shots (
                id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL)""")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create(self, shot: ShotDocument) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO svg_shots VALUES (?, ?, ?)",
                (shot.id, shot.version, shot.model_dump_json(by_alias=True)),
            )

    def load(self, shot_id: str) -> ShotDocument | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM svg_shots WHERE id = ?", (shot_id,)
            ).fetchone()
        return ShotDocument.model_validate_json(row[0]) if row else None

    def save(self, shot: ShotDocument, expected_version: int) -> None:
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE svg_shots SET version = ?, payload = ? WHERE id = ? AND version = ?",
                (shot.version, shot.model_dump_json(by_alias=True), shot.id, expected_version),
            ).rowcount
            if changed != 1:
                raise ShotConflict("镜头已在其他页面修改，本次结果未覆盖现有画面")
