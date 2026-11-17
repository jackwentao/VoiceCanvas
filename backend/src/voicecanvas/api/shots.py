"""单镜头 API；模型请求在线程池内执行，不阻塞其他 API。"""

import threading
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from voicecanvas.adapters.llm.svg_shot import ShotModelError
from voicecanvas.application.shot_service import ShotConflict, ShotNotFound, ShotService
from voicecanvas.domain.shot import ShotDocument
from voicecanvas.domain.svg_text import list_text_blocks


class CreateShot(BaseModel):
    title: str = Field(default="未命名镜头", max_length=100)


class ShotChange(BaseModel):
    expected_version: int = Field(alias="expectedVersion", ge=0)


class GenerateShot(ShotChange):
    instruction: str = Field(min_length=1, max_length=4000)

    @field_validator("instruction")
    @classmethod
    def meaningful_instruction(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请描述你想画的镜头或修改")
        return value.strip()


class EditShotText(ShotChange):
    index: int = Field(ge=0)
    lines: list[str] = Field(min_length=1, max_length=100)
    font_size: float = Field(alias="fontSize", ge=8, le=160, allow_inf_nan=False)
    line_height: float = Field(default=1.35, alias="lineHeight", ge=1, le=3, allow_inf_nan=False)
    y: float = Field(ge=-10000, le=10000, allow_inf_nan=False)


def present_shot(shot: ShotDocument) -> dict:
    return {
        "id": shot.id,
        "title": shot.title,
        "version": shot.version,
        "svg": shot.svg,
        "texts": list_text_blocks(shot.svg),
        "cursor": shot.cursor,
        "canUndo": shot.cursor >= 0,
        "canRedo": shot.cursor + 1 < len(shot.revisions),
        "revisions": [
            {
                "instruction": r.instruction,
                "createdAt": r.created_at,
                "usage": r.usage,
                "model": r.model,
            }
            for r in shot.revisions
        ],
    }


def create_shot_router(factory: Callable[[], ShotService]) -> APIRouter:
    router = APIRouter(prefix="/api/shots", tags=["single-shot"])
    service: ShotService | None = None
    lock = threading.Lock()

    def get_service() -> ShotService:
        nonlocal service
        with lock:
            if service is None:
                service = factory()
            return service

    def execute(action: Callable[[], ShotDocument]) -> dict:
        try:
            return present_shot(action())
        except ShotNotFound as error:
            raise HTTPException(404, str(error)) from error
        except ShotConflict as error:
            raise HTTPException(409, str(error)) from error
        except ShotModelError as error:
            raise HTTPException(502, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.post("", status_code=201)
    def create(request: CreateShot) -> dict:
        return execute(lambda: get_service().create(request.title))

    @router.get("/{shot_id}")
    def get(shot_id: str) -> dict:
        return execute(lambda: get_service().get(shot_id))

    @router.post("/{shot_id}/generate")
    def generate(shot_id: str, request: GenerateShot) -> dict:
        return execute(
            lambda: get_service().generate(shot_id, request.expected_version, request.instruction)
        )

    @router.post("/{shot_id}/text")
    def edit_text(shot_id: str, request: EditShotText) -> dict:
        return execute(
            lambda: get_service().edit_text(
                shot_id,
                request.expected_version,
                request.index,
                request.lines,
                request.font_size,
                request.line_height,
                request.y,
            )
        )

    @router.post("/{shot_id}/{action}")
    def history(shot_id: str, action: Literal["undo", "redo"], request: ShotChange) -> dict:
        return execute(
            lambda: get_service().move(
                shot_id, request.expected_version, -1 if action == "undo" else 1
            )
        )

    @router.get("/{shot_id}/export.svg")
    def export_svg(shot_id: str) -> Response:
        state = execute(lambda: get_service().get(shot_id))
        if not state["svg"]:
            raise HTTPException(409, "当前镜头还没有画面")
        return Response(
            state["svg"],
            media_type="image/svg+xml",
            headers={
                "Content-Disposition": 'attachment; filename="voicecanvas-shot.svg"',
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
