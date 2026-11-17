"""分镜编排 API，语音转写与文字使用相同命令入口，不调用绘图模型。"""

import threading
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from voicecanvas.api.shots import ShotChange, present_shot
from voicecanvas.application.shot_service import ShotConflict, ShotNotFound
from voicecanvas.application.storyboard_commands import parse_board_command
from voicecanvas.application.storyboard_service import StoryboardService
from voicecanvas.domain.storyboard import Storyboard


class CreateStoryboard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="未命名分镜", min_length=1, max_length=100)


class StoryboardChange(ShotChange):
    action: Literal[
        "add", "switch", "rename", "rename_project", "move", "duplicate", "delete", "undo", "redo"
    ]
    target_id: str | None = Field(default=None, alias="targetId", max_length=100)
    title: str | None = Field(default=None, max_length=100)
    position: int | None = Field(default=None, ge=1, le=40)
    count: int = Field(default=1, ge=1, le=12)
    confirmed: bool = False


class StoryboardTranscript(ShotChange):
    transcript: str = Field(min_length=1, max_length=4000)


def present_storyboard(service: StoryboardService, board: Storyboard) -> dict:
    shots = service.repository.load_shots([shot.id for shot in board.state.shots])
    if board.active_id not in shots:
        raise ShotNotFound("当前镜头内容不存在")
    return {
        "id": board.id,
        "version": board.version,
        "title": board.state.title,
        "context": board.state.context,
        "activeId": board.active_id,
        "canUndo": board.cursor > 0,
        "canRedo": board.cursor + 1 < len(board.states),
        "shots": [
            {
                **shot.model_dump(by_alias=True),
                "svg": shots[shot.id].svg,
                "version": shots[shot.id].version,
            }
            for shot in board.state.shots
        ],
        "activeShot": present_shot(shots[board.active_id]),
    }


def create_storyboard_router(factory: Callable[[], StoryboardService]) -> APIRouter:
    router = APIRouter(prefix="/api/storyboards", tags=["storyboards"])
    service: StoryboardService | None = None
    lock = threading.Lock()

    def get_service() -> StoryboardService:
        nonlocal service
        with lock:
            if service is None:
                service = factory()
        return service

    def present(board: Storyboard) -> dict:
        return present_storyboard(get_service(), board)

    def execute(action):
        try:
            return action()
        except ShotNotFound as error:
            raise HTTPException(404, str(error)) from error
        except ShotConflict as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.post("", status_code=201)
    def create(request: CreateStoryboard) -> dict:
        return execute(lambda: present(get_service().create(request.title)))

    @router.get("")
    def recent() -> list[dict]:
        return execute(
            lambda: [
                {"id": board.id, "title": board.state.title, "count": len(board.state.shots)}
                for board in get_service().repository.list_recent()
            ]
        )

    @router.get("/{board_id}")
    def get(board_id: str) -> dict:
        return execute(lambda: present(get_service().get(board_id)))

    @router.post("/{board_id}/manage")
    def manage(board_id: str, request: StoryboardChange) -> dict:
        return execute(
            lambda: present(
                get_service().change(
                    board_id,
                    request.expected_version,
                    request.action,
                    request.target_id,
                    request.title,
                    request.position,
                    request.count,
                    request.confirmed,
                )
            )
        )

    @router.post("/{board_id}/command")
    def command(board_id: str, request: StoryboardTranscript) -> dict:
        def run():
            board = get_service().current(board_id, request.expected_version)
            parsed = parse_board_command(request.transcript, board)
            if parsed.action in {
                "confirm",
                "cancel",
                "draw",
                "list",
                "request_delete",
                "undo_shot",
                "redo_shot",
                "new_project",
                "export_png",
                "export_svg",
            }:
                if parsed.action == "request_delete" and len(board.state.shots) == 1:
                    raise ValueError("至少保留一个镜头，可新建镜头后再删除")
                return {
                    "board": present(board),
                    "action": parsed.action,
                    "targetId": parsed.target_id,
                    "instruction": parsed.instruction,
                }
            result = get_service().change(
                board_id,
                board.version,
                parsed.action,
                parsed.target_id,
                parsed.title,
                parsed.position,
                parsed.count,
            )
            return {
                "board": present(result),
                "action": "draw" if parsed.instruction else parsed.action,
                "instruction": parsed.instruction,
                "targetId": result.active_id,
            }

        return execute(run)

    return router
