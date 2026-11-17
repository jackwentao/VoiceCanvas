"""任务提交快速返回；浏览器通过已持久化任务读取进展，不占用长连接。"""

import threading
from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import Field

from voicecanvas.api.shots import ShotChange
from voicecanvas.api.storyboards import present_storyboard
from voicecanvas.application.shot_service import ShotConflict, ShotNotFound
from voicecanvas.application.storyboard_agent_service import StoryboardAgentService


class AgentRequest(ShotChange):
    request: str = Field(min_length=1, max_length=8000)


def create_agent_router(factory: Callable[[], StoryboardAgentService]) -> APIRouter:
    router = APIRouter(prefix="/api/storyboards", tags=["storyboard-agent"])
    service = None
    lock = threading.Lock()

    def get_service() -> StoryboardAgentService:
        nonlocal service
        with lock:
            if service is None:
                service = factory()
        return service

    def execute(board_id, request=None):
        try:
            current = get_service()
            run = (
                current.start(board_id, request.expected_version, request.request)
                if request
                else current.get(board_id)
            )
            return {
                "run": run.model_dump(by_alias=True) if run else None,
                "board": present_storyboard(current.boards, current.boards.get(board_id)),
            }
        except ShotNotFound as error:
            raise HTTPException(404, str(error)) from error
        except ShotConflict as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.post("/{board_id}/agent/runs", status_code=202)
    def start(board_id: str, request: AgentRequest):
        return execute(board_id, request)

    @router.get("/{board_id}/agent/run")
    def latest(board_id: str):
        return execute(board_id)

    @router.get("/{board_id}/shots/{shot_id}/previews/{image_id}.png")
    def preview(board_id: str, shot_id: str, image_id: str):
        try:
            visual = get_service().visuals
            if visual is None:
                raise HTTPException(503, "当前服务未配置预览渲染")
            return Response(
                visual.read(board_id, shot_id, image_id),
                media_type="image/png",
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )
        except ShotNotFound as error:
            raise HTTPException(404, str(error)) from error
        except ShotConflict as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    return router
