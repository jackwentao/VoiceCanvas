"""内容键缓存，不接受客户端路径，缓存目录跟随项目数据库放置。"""

import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from voicecanvas.domain.shot_preview import png_dimensions


class FilePreviewStore:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, image_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", image_id):
            raise ValueError("预览标识无效")
        return self.root / f"{image_id}.png"

    def get(self, image_id: str) -> bytes | None:
        path = self._path(image_id)
        if not path.is_file():
            return None
        if path.stat().st_size > 8_000_000:
            raise ValueError("预览缓存超过资源限制")
        image = path.read_bytes()
        if png_dimensions(image) != (1280, 720):
            raise ValueError("预览缓存损坏，请清理对应缓存文件后重试")
        return image

    def put(self, image_id: str, image: bytes) -> None:
        target = self._path(image_id)
        if png_dimensions(image) != (1280, 720):
            raise ValueError("预览尺寸不符")
        self.root.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=self.root, delete=False, suffix=".tmp") as file:
            temporary = Path(file.name)
            file.write(image)
        try:
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
