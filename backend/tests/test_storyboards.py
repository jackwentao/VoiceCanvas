"""真实 SQLite 下的结构化分镜管理和画面隔离。"""

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voicecanvas.api.shots import create_shot_router
from voicecanvas.api.storyboards import create_storyboard_router
from voicecanvas.application.shot_service import ShotConflict, ShotService
from voicecanvas.application.storyboard_service import StoryboardService
from voicecanvas.infrastructure.sqlite_shot_repository import SQLiteShotRepository
from voicecanvas.infrastructure.sqlite_storyboard_repository import SQLiteStoryboardRepository

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
    '<rect width="1280" height="720" fill="navy"/>'
    '<text x="50" y="80">雨夜</text></svg>'
)


class Generator:
    def __init__(self):
        self.calls = []

    def generate(self, instruction, source):
        self.calls.append((instruction, source))
        return SVG.replace("雨夜", instruction), {}, "fixture"


@pytest.fixture
def services(tmp_path):
    db = tmp_path / "storyboards.sqlite3"
    repo = SQLiteStoryboardRepository(db)
    generator = Generator()
    shots = ShotService(SQLiteShotRepository(db), generator)
    return StoryboardService(repo), shots, generator


def test_lifecycle_order_rename_restore_and_independent_picture_history(services):
    boards, shots, generator = services
    board = boards.create("雨夜故事")
    first_id = board.active_id
    picture = shots.generate(first_id, 0, "女孩等雨")
    board = boards.change(board.id, 0, "add", count=2)
    second_id, third_id = [s.id for s in board.state.shots[1:]]
    assert board.active_id == second_id
    second_picture = shots.generate(second_id, 0, "朋友走来")
    board = boards.change(board.id, 1, "rename", second_id, title="相遇")
    board = boards.change(board.id, 2, "move", third_id, position=1)
    assert [s.id for s in board.state.shots] == [third_id, first_id, second_id]
    board = boards.change(board.id, 3, "switch", first_id)
    board = boards.change(board.id, 4, "delete", second_id, confirmed=True)
    assert len(board.state.shots) == 2
    assert shots.get(second_id).svg == second_picture.svg
    board = boards.change(board.id, 5, "undo")
    assert len(board.state.shots) == 3 and board.state.shots[2].title == "相遇"
    board = boards.change(board.id, 6, "redo")
    assert len(board.state.shots) == 2
    assert shots.get(first_id).svg == picture.svg
    assert len(generator.calls) == 2
    reloaded = StoryboardService(SQLiteStoryboardRepository(boards.repository.db_path)).get(
        board.id
    )
    assert reloaded == board


def test_svg_import_roundtrip_preserves_existing_shots_and_validates_before_write(services):
    boards, shots, generator = services
    app = FastAPI()
    app.include_router(create_storyboard_router(lambda: boards))
    app.include_router(create_shot_router(lambda: shots))
    board = boards.create("导入分镜")
    path = f"/api/storyboards/{board.id}"
    with TestClient(app) as client:
        rejected = client.post(f"{path}/import-svg", json={
            "expectedVersion": 0, "title": "损坏的图", "svg": "<svg />",
        })
        assert rejected.status_code == 422
        assert boards.get(board.id) == board
        first = client.post(f"{path}/import-svg", json={
            "expectedVersion": 0, "title": "雨夜", "svg": SVG,
        })
        assert first.status_code == 201, first.text
        imported = first.json()
        assert len(imported["shots"]) == 1
        first_id = imported["activeId"]
        assert first_id != board.active_id
        assert imported["activeShot"]["texts"][0]["text"] == "雨夜"
        exported = client.get(f"/api/shots/{first_id}/export.svg").text
        second = client.post(f"{path}/import-svg", json={
            "expectedVersion": 1, "title": "第二镜", "svg": exported,
        })
        assert second.status_code == 201
        assert len(second.json()["shots"]) == 2
        assert second.json()["activeShot"]["svg"] == exported
        stale = client.post(f"{path}/import-svg", json={
            "expectedVersion": 1, "title": "冲突", "svg": SVG,
        })
        assert stale.status_code == 409
        assert len(client.get(path).json()["shots"]) == 2
        assert boards.change(board.id, 2, "undo").active_id == first_id
        assert boards.change(board.id, 3, "undo").active_id == board.active_id
        assert not shots.get(board.active_id).svg
        assert not generator.calls


def test_duplicate_snapshots_current_picture_and_does_not_share_history(services):
    boards, shots, _ = services
    board = boards.create("故事")
    original = board.active_id
    shots.generate(original, 0, "第一版")
    shots.generate(original, 1, "第二版")
    board = boards.change(board.id, 0, "duplicate")
    duplicate = board.active_id
    assert shots.get(duplicate).svg == shots.get(original).svg
    assert len(shots.get(duplicate).revisions) == 1
    shots.generate(duplicate, 0, "副本修改")
    assert "第二版" in shots.get(original).svg
    assert "副本修改" in shots.get(duplicate).svg
    shots.move(duplicate, 1, -1)
    assert "第二版" in shots.get(duplicate).svg


def test_management_preserves_selection_after_nonhistorical_switch(services):
    boards, _, _ = services
    board = boards.create("选择保持")
    first = board.active_id
    board = boards.change(board.id, 0, "add")
    second = board.active_id
    board = boards.change(board.id, 1, "switch", first)
    board = boards.change(board.id, 2, "rename", second, title="相遇")
    assert board.active_id == first
    board = boards.change(board.id, 3, "move", second, position=1)
    assert board.active_id == first


def test_delete_requires_confirmation_last_shot_and_wrong_target_rejected(services):
    boards, _, _ = services
    board = boards.create("项目")
    with pytest.raises(ValueError, match="确认"):
        boards.change(board.id, 0, "delete")
    with pytest.raises(ValueError, match="保留"):
        boards.change(board.id, 0, "delete", confirmed=True)
    with pytest.raises(ValueError, match="不属于"):
        boards.change(board.id, 0, "switch", "shot_foreign")
    with pytest.raises(ValueError):
        boards.change(board.id, 0, "add", count=13)
    assert boards.get(board.id).version == 0


def test_stale_add_is_atomic_no_orphan_shots_and_redo_branch_truncated(services):
    boards, _, _ = services
    board = boards.create("项目")
    boards.change(board.id, 0, "add")
    with pytest.raises(ShotConflict):
        boards.change(board.id, 0, "add", count=3)
    with sqlite3.connect(boards.repository.db_path) as connection:
        assert connection.execute("SELECT count(*) FROM svg_shots").fetchone()[0] == 2
    board = boards.change(board.id, 1, "undo")
    board = boards.change(board.id, 2, "rename_project", title="新名称")
    assert len(board.states) == 2
    with pytest.raises(ValueError, match="没有"):
        boards.change(board.id, 3, "redo")


def test_structured_api_and_picture_history_are_separate(services):
    boards, shots, generator = services
    app = FastAPI()
    app.include_router(create_storyboard_router(lambda: boards))
    app.include_router(create_shot_router(lambda: shots))
    with TestClient(app) as client:
        board = client.post("/api/storyboards", json={"title": "故事"}).json()
        path = f"/api/storyboards/{board['id']}"
        assert client.post(path + "/command", json={}).status_code == 404
        board = client.post(
            path + "/manage",
            json={
                "expectedVersion": 0,
                "action": "add",
                "count": 2,
            },
        ).json()
        assert len(board["shots"]) == 3 and not generator.calls
        assert (
            client.post(
                path + "/manage",
                json={
                    "expectedVersion": 0,
                    "action": "add",
                },
            ).status_code
            == 409
        )
        sid = board["activeId"]
        assert (
            client.post(
                f"/api/shots/{sid}/generate",
                json={
                    "expectedVersion": 0,
                    "instruction": "雨夜",
                },
            ).status_code
            == 200
        )
        loaded = client.get(path).json()
        assert "雨夜" in loaded["activeShot"]["svg"]
        assert loaded["version"] == 1 and loaded["activeShot"]["version"] == 1
        deletion = {"expectedVersion": 1, "action": "delete", "targetId": sid}
        assert client.post(path + "/manage", json=deletion).status_code == 422
        assert (
            len(
                client.post(
                    path + "/manage",
                    json={
                        **deletion,
                        "confirmed": True,
                    },
                ).json()["shots"]
            )
            == 2
        )
