from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol
from urllib.parse import quote

CATALOG_ASSET_PREFIX = "catalog/commerce/"


class CatalogAssetPathError(ValueError):
    """素材路径不符合 Catalog 允许范围。"""


class CatalogAssetUnavailableError(RuntimeError):
    """素材后端当前不可用。"""


@dataclass(frozen=True)
class CatalogAssetRef:
    path: str
    provider: str
    url: str


@dataclass(frozen=True)
class CatalogAssetContent:
    content: bytes
    media_type: str


class AssetStorage(Protocol):
    """素材存储端口；具体 MinIO/本地实现不能进入领域层。"""

    def catalog_asset_url(self, path: str) -> CatalogAssetRef:
        """返回前端可渲染的后端代理 URL。"""

    def read_catalog_asset(self, path: str) -> CatalogAssetContent:
        """读取素材内容，用于后端代理图片响应。"""


def validate_catalog_asset_path(path: str) -> str:
    normalized = str(path or "").strip().replace("\\", "/")
    if not normalized:
        raise CatalogAssetPathError("素材路径不能为空")
    if normalized.startswith("/") or normalized.startswith("./"):
        raise CatalogAssetPathError("素材路径必须是相对对象路径")
    if not normalized.startswith(CATALOG_ASSET_PREFIX):
        raise CatalogAssetPathError(f"素材路径必须位于 {CATALOG_ASSET_PREFIX} 前缀下")

    parts = PurePosixPath(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise CatalogAssetPathError("素材路径不能包含空段、. 或 ..")
    return "/".join(parts)


def catalog_proxy_url(path: str) -> str:
    safe_path = validate_catalog_asset_path(path)
    return f"/api/assets/catalog/raw?path={quote(safe_path, safe='')}"


def media_type_from_path(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"
