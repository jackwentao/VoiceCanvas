"""真实 SQLite 下的分镜编排、语音转写路由和画面隔离。"""

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voicecanvas.api.shots import create_shot_router
from voicecanvas.api.storyboards import create_storyboard_router
from voicecanvas.application.shot_service import ShotConflict, ShotService
from voicecanvas.application.storyboard_commands import number, parse_board_command
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


@pytest.mark.parametrize(
    "raw,expected", [("两", 2), ("十二", 12), ("四十", 40), ("三十一", 31), ("10", 10)]
)
def test_spoken_number(raw, expected):
    assert number(raw) == expected


@pytest.mark.parametrize(
    "text,action,position,count",
    [
        ("新建三个镜头。", "add", None, 3),
        ("再加两个镜头，", "add", None, 2),
        ("创建一个分镜", "add", None, 1),
        ("新建分镜项目", "new_project", None, 1),
        ("导出 SVG", "export_svg", None, 1),
        ("导出当前镜头", "export_png", None, 1),
        ("取消删除", "cancel", None, 1),
        ("切换到第二个镜头", "switch", None, 1),
        ("把第三个镜头移到第一位", "move", 1, 1),
        ("当前镜头改名为雨夜", "rename", None, 1),
        ("删除最后一个镜头", "request_delete", None, 1),
        ("复制第二个镜头", "duplicate", None, 1),
        ("撤销分镜操作", "undo", None, 1),
        ("确认删除", "confirm", None, 1),
        ("查看分镜", "list", None, 1),
        ("第二个镜头画一个拿伞的女孩", "draw", None, 1),
        ("新建一个镜头，画便利店门口", "add", None, 1),
        ("把雨衣改成红色", "draw", None, 1),
        ("把对白改成删除第二个镜头", "draw", None, 1),
    ],
)
def test_voice_routes_complete_commands_only(services, text, action, position, count):
    boards, _, _ = services
    board = boards.create("故事")
    board = boards.change(board.id, 0, "add", count=2)
    result = parse_board_command(text, board)
    assert result.action == action and result.position == position and result.count == count
    if text.startswith("新建一个镜头，"):
        assert result.instruction == "画便利店门口"


@pytest.mark.parametrize(
    "text",
    [
        "切换到第五个镜头",
        "删除第二个镜头并画一只猫",
        "新建三个镜头然后删除第一个",
        "把第二个镜头放到右边",
        "新建零个镜头",
    ],
)
def test_ambiguous_or_invalid_management_does_not_become_drawing(services, text):
    boards, _, _ = services
    board = boards.create("项目")
    if text == "新建零个镜头":
        command = parse_board_command(text, board)
        with pytest.raises(ValueError):
            boards.change(board.id, 0, command.action, count=command.count)
    else:
        with pytest.raises(ValueError):
            parse_board_command(text, board)


def test_api_transcript_manage_and_picture_are_separate(services):
    boards, shots, generator = services
    app = FastAPI()
    app.include_router(create_storyboard_router(lambda: boards))
    app.include_router(create_shot_router(lambda: shots))
    with TestClient(app) as client:
        assert client.post(
            "/api/storyboards", json={"existingShotId": "shot_legacy"}
        ).status_code == 422
        board = client.post("/api/storyboards", json={"title": "故事"}).json()
        board_id = board["id"]
        response = client.post(
            f"/api/storyboards/{board_id}/command",
            json={"expectedVersion": 0, "transcript": "新建两个镜头"},
        )
        assert response.status_code == 200
        board = response.json()["board"]
        assert len(board["shots"]) == 3 and generator.calls == []
        assert (
            client.post(
                f"/api/storyboards/{board_id}/command",
                json={"expectedVersion": 0, "transcript": "删除当前镜头"},
            ).status_code
            == 409
        )
        response = client.post(
            f"/api/storyboards/{board_id}/command",
            json={"expectedVersion": 1, "transcript": "删除第一个镜头"},
        ).json()
        assert response["action"] == "request_delete" and len(response["board"]["shots"]) == 3
        request = {"expectedVersion": 1, "action": "delete", "targetId": board["shots"][0]["id"]}
        assert client.post(f"/api/storyboards/{board_id}/manage", json=request).status_code == 422
        board = client.post(
            f"/api/storyboards/{board_id}/manage", json={**request, "confirmed": True}
        ).json()
        assert len(board["shots"]) == 2
        target = board["activeId"]
        assert (
            client.post(
                f"/api/shots/{target}/generate", json={"expectedVersion": 0, "instruction": "雨夜"}
            ).status_code
            == 200
        )
        loaded = client.get(f"/api/storyboards/{board_id}").json()
        assert "雨夜" in loaded["activeShot"]["svg"]
        assert loaded["version"] == 2 and loaded["activeShot"]["version"] == 1
        assert client.get("/api/storyboards").json()[0]["count"] == 2
        assert (
            client.post(
                f"/api/storyboards/{board_id}/manage", json={"expectedVersion": 2, "action": "undo"}
            ).json()["shots"][0]["id"]
            == request["targetId"]
        )
