"""版本绑定的真实预览；领域逻辑不依赖浏览器、HTTP 或文件系统。"""

from hashlib import sha256
from typing import Protocol

from voicecanvas.application.shot_service import ShotConflict, ShotService
from voicecanvas.application.storyboard_service import StoryboardService
from voicecanvas.domain.shot_preview import png_dimensions


class ShotRenderer(Protocol):
    identity: str

    def render(self, svg: str) -> bytes: ...


class ShotReviewer(Protocol):
    def review_image(self, image: bytes, brief: str, focus: str = "") -> tuple[str, dict]: ...


class PreviewStore(Protocol):
    def get(self, image_id: str) -> bytes | None: ...
    def put(self, image_id: str, image: bytes) -> None: ...


class ShotVisualService:
    def __init__(
        self,
        boards: StoryboardService,
        shots: ShotService,
        renderer: ShotRenderer,
        store: PreviewStore,
    ):
        self.boards, self.shots, self.renderer, self.store = boards, shots, renderer, store

    def _source(self, board_id: str, shot_id: str):
        board = self.boards.get(board_id)
        if shot_id not in {s.id for s in board.state.shots}:
            raise ValueError("目标镜头不属于当前项目")
        shot = self.shots.get(shot_id)
        if not shot.svg:
            raise ValueError("当前镜头还没有画面，不能渲染")
        source_hash = sha256(shot.svg.encode("utf-8")).hexdigest()
        image_id = sha256(
            f"{board_id}:{shot_id}:{shot.version}:{source_hash}:{self.renderer.identity}".encode()
        ).hexdigest()
        return shot, source_hash, image_id

    def render(self, board_id: str, shot_id: str) -> dict:
        shot, source_hash, image_id = self._source(board_id, shot_id)
        image = self.store.get(image_id)
        if image is None:
            image = self.renderer.render(shot.svg)
            if png_dimensions(image) != (1280, 720):
                raise ValueError("渲染尺寸不符，未向模型提交图片")
            self.store.put(image_id, image)
        if self.shots.get(shot_id).version != shot.version:
            raise ShotConflict("渲染期间镜头已变化，请重新获取当前预览")
        return {
            "shotId": shot_id,
            "shotVersion": shot.version,
            "svgSha256": source_hash,
            "imageId": image_id,
            "width": 1280,
            "height": 720,
            "bytes": len(image),
            "renderer": self.renderer.identity,
            "previewUrl": f"/api/storyboards/{board_id}/shots/{shot_id}/previews/{image_id}.png",
            "visualReview": "rendered_only",
        }

    def read(self, board_id: str, shot_id: str, image_id: str) -> bytes:
        shot, _, current_id = self._source(board_id, shot_id)
        if image_id != current_id:
            raise ShotConflict("预览不是当前画面版本，请重新渲染")
        image = self.store.get(image_id)
        if image is None:
            raise ValueError("预览文件不存在，请重新渲染")
        if self.shots.get(shot_id).version != shot.version:
            raise ShotConflict("读取期间镜头已变化，请重新获取当前预览")
        return image
