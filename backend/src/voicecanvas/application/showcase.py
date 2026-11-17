"""后端维护的原创展示画廊；展示资源与用户项目存储相互独立。"""

import json
from pathlib import Path
from typing import Any


class ShowcaseCatalog:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path(__file__).resolve().parents[1] / "resources" / "showcase"
        self._manifest = json.loads((self._root / "catalog.json").read_text(encoding="utf-8"))

    def list(self, category: str | None = None) -> dict[str, Any]:
        categories = self._manifest["categories"]
        if category and category not in {item["id"] for item in categories}:
            raise ValueError("未找到这个作品分类")
        items = [
            {**item, "imageUrl": f"/api/showcase/{item['id']}/artwork"}
            for item in self._manifest["items"]
            if not category or item["category"] == category
        ]
        return {"categories": categories, "items": items, "total": len(items)}

    def artwork(self, artwork_id: str) -> bytes:
        # 文件名来自服务器白名单，不接受用户输入作为文件路径。
        item = next((item for item in self._manifest["items"] if item["id"] == artwork_id), None)
        if item is None:
            raise ValueError("未找到这幅作品")
        return (self._root / item["file"]).read_bytes()
