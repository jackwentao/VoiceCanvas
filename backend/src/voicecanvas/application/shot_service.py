"""单镜头创作应用层，只依赖生成器和仓储端口。"""

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from voicecanvas.domain.shot import ShotDocument, ShotRevision
from voicecanvas.domain.svg_document import validate_svg


class ShotConflict(ValueError):
    pass


class ShotNotFound(ValueError):
    pass


class ShotGenerator(Protocol):
    def generate(
        self, instruction: str, current_svg: str | None
    ) -> tuple[str, dict[str, int], str]:
        """返回候选 SVG、用量和模型标识，不直接修改可信文档。"""
        ...


class ShotRepository(Protocol):
    def create(self, shot: ShotDocument) -> None: ...
    def load(self, shot_id: str) -> ShotDocument | None: ...
    def save(self, shot: ShotDocument, expected_version: int) -> None: ...


class ShotService:
    def __init__(self, repository: ShotRepository, generator: ShotGenerator) -> None:
        self.repository = repository
        self.generator = generator

    def create(self, title: str) -> ShotDocument:
        shot = ShotDocument(id=f"shot_{uuid4().hex[:16]}", title=title.strip() or "未命名镜头")
        self.repository.create(shot)
        return shot

    def get(self, shot_id: str) -> ShotDocument:
        shot = self.repository.load(shot_id)
        if shot is None:
            raise ShotNotFound("镜头不存在")
        return shot

    def _editable(self, shot_id: str, expected_version: int) -> ShotDocument:
        shot = self.get(shot_id)
        if shot.version != expected_version:
            raise ShotConflict("镜头已在其他页面修改，请刷新后重试")
        return shot

    def generate(self, shot_id: str, expected_version: int, instruction: str) -> ShotDocument:
        shot = self._editable(shot_id, expected_version)
        if shot.cursor >= 39:
            raise ValueError("当前镜头已保存 40 个版本，请新建镜头继续创作")
        svg, usage, model = self.generator.generate(instruction, shot.svg)
        svg = validate_svg(svg)
        revision = ShotRevision(
            svg=svg,
            instruction=instruction,
            usage=usage,
            model=model,
            createdAt=datetime.now(UTC).isoformat(),
        )
        next_shot = shot.model_copy(
            update={
                "revisions": [*shot.revisions[: shot.cursor + 1], revision],
                "cursor": shot.cursor + 1,
                "version": shot.version + 1,
            }
        )
        # 模型调用期间文档可能被另一请求改动，仓储必须再次原子检查版本。
        self.repository.save(next_shot, expected_version)
        return next_shot

    def move(self, shot_id: str, expected_version: int, direction: int) -> ShotDocument:
        shot = self._editable(shot_id, expected_version)
        cursor = shot.cursor + direction
        if not -1 <= cursor < len(shot.revisions):
            raise ValueError("没有可以撤销或重做的版本")
        next_shot = shot.model_copy(update={"cursor": cursor, "version": shot.version + 1})
        self.repository.save(next_shot, expected_version)
        return next_shot
