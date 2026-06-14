from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx

from voicecanvas.application.asset_storage import (
    CatalogAssetContent,
    CatalogAssetRef,
    CatalogAssetUnavailableError,
    catalog_proxy_url,
    media_type_from_path,
    validate_catalog_asset_path,
)


@dataclass(frozen=True)
class MinioAssetStorageConfig:
    endpoint: str | None = None
    bucket: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    secure: bool = False
    public_base_url: str | None = None


class MinioAssetStorage:
    """MinIO 素材存储适配器。

    Catalog 对外只暴露后端代理 URL；真实对象读取集中在这里，避免前端接触 MinIO
    凭证或桶结构。
    """

    def __init__(self, config: MinioAssetStorageConfig) -> None:
        self._config = config

    def catalog_asset_url(self, path: str) -> CatalogAssetRef:
        safe_path = validate_catalog_asset_path(path)
        return CatalogAssetRef(path=safe_path, provider="minio", url=catalog_proxy_url(safe_path))

    def read_catalog_asset(self, path: str) -> CatalogAssetContent:
        safe_path = validate_catalog_asset_path(path)
        if self._config.public_base_url:
            return self._read_public_asset(safe_path)
        return self._read_minio_asset(safe_path)

    def _read_public_asset(self, path: str) -> CatalogAssetContent:
        base_url = self._config.public_base_url
        if base_url is None:
            raise CatalogAssetUnavailableError("公开素材地址未配置")
        url = f"{base_url.rstrip('/')}/{quote(path)}"
        try:
            response = httpx.get(url, timeout=10)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise CatalogAssetUnavailableError(f"公开素材地址不可用：{error}") from error
        return CatalogAssetContent(
            content=response.content,
            media_type=response.headers.get("content-type") or media_type_from_path(path),
        )

    def _read_minio_asset(self, path: str) -> CatalogAssetContent:
        config = self._config
        if not all([config.endpoint, config.bucket, config.access_key, config.secret_key]):
            raise CatalogAssetUnavailableError("MinIO 配置不完整，无法读取素材")

        try:
            from minio import Minio
            from minio.error import S3Error
        except ImportError as error:
            raise CatalogAssetUnavailableError("未安装 MinIO SDK，无法读取私有桶素材") from error

        client = Minio(
            config.endpoint or "",
            access_key=config.access_key,
            secret_key=config.secret_key,
            secure=config.secure,
        )
        response = None
        try:
            response = client.get_object(config.bucket or "", path)
            content = response.read()
        except S3Error as error:
            raise CatalogAssetUnavailableError(f"MinIO 素材读取失败：{error}") from error
        finally:
            if response is not None:
                response.close()
                response.release_conn()

        return CatalogAssetContent(content=content, media_type=media_type_from_path(path))
