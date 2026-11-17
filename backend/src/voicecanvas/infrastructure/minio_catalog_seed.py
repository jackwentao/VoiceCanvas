from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Protocol

from voicecanvas.application.asset_storage import media_type_from_path, validate_catalog_asset_path


@dataclass(frozen=True)
class CatalogSeedAsset:
    render_key: str
    display_name: str
    asset_path: str


@dataclass(frozen=True)
class CatalogSeedResult:
    asset_path: str
    source: str
    byte_size: int
    uploaded: bool


@dataclass(frozen=True)
class CatalogCheckResult:
    asset_path: str
    exists: bool
    detail: str | None = None


class MinioCatalogNotReadyError(RuntimeError):
    """MinIO 素材包未完成上传时抛出的启动前检查错误。"""


class MinioSeedClient(Protocol):
    def bucket_exists(self, bucket_name: str) -> bool: ...

    def make_bucket(self, bucket_name: str) -> None: ...

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BytesIO,
        length: int,
        content_type: str,
    ) -> object: ...


class MinioCatalogCheckClient(Protocol):
    def bucket_exists(self, bucket_name: str) -> bool: ...

    def stat_object(self, bucket_name: str, object_name: str) -> object: ...


def default_render_catalog_path() -> Path:
    return Path(__file__).resolve().parents[1] / "resources" / "render-catalog.json"


def load_catalog_seed_assets(catalog_path: Path | None = None) -> list[CatalogSeedAsset]:
    path = catalog_path or default_render_catalog_path()
    with path.open("r", encoding="utf-8") as file:
        catalog = json.load(file)

    assets: dict[str, CatalogSeedAsset] = {}
    for item in catalog.get("items", []):
        if item.get("assetProvider") != "minio" or not item.get("assetPath"):
            continue
        asset_path = validate_catalog_asset_path(str(item["assetPath"]))
        assets[asset_path] = CatalogSeedAsset(
            render_key=str(item.get("renderKey") or Path(asset_path).stem),
            display_name=str(item.get("displayName") or Path(asset_path).stem),
            asset_path=asset_path,
        )
    return list(assets.values())


def seed_minio_catalog(
    client: MinioSeedClient,
    bucket: str,
    assets: list[CatalogSeedAsset],
    *,
    asset_root: Path | None = None,
    generate_placeholders: bool = False,
    dry_run: bool = False,
) -> list[CatalogSeedResult]:
    if not bucket.strip():
        raise ValueError("MinIO bucket 不能为空")

    if not dry_run and not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    results: list[CatalogSeedResult] = []
    for asset in assets:
        payload, source = _resolve_payload(
            asset,
            asset_root=asset_root,
            generate_placeholders=generate_placeholders,
        )
        content_type = media_type_from_path(asset.asset_path)
        if not dry_run:
            client.put_object(
                bucket,
                asset.asset_path,
                BytesIO(payload),
                len(payload),
                content_type=content_type,
            )
        results.append(
            CatalogSeedResult(
                asset_path=asset.asset_path,
                source=source,
                byte_size=len(payload),
                uploaded=not dry_run,
            )
        )
    return results


def check_minio_catalog(
    client: MinioCatalogCheckClient,
    bucket: str,
    assets: list[CatalogSeedAsset],
) -> list[CatalogCheckResult]:
    if not bucket.strip():
        raise ValueError("MinIO bucket 不能为空")

    if not client.bucket_exists(bucket):
        return [
            CatalogCheckResult(
                asset_path=asset.asset_path,
                exists=False,
                detail=f"bucket 不存在：{bucket}",
            )
            for asset in assets
        ]

    results: list[CatalogCheckResult] = []
    for asset in assets:
        try:
            client.stat_object(bucket, asset.asset_path)
        except Exception as error:
            results.append(
                CatalogCheckResult(
                    asset_path=asset.asset_path,
                    exists=False,
                    detail=str(error),
                )
            )
        else:
            results.append(CatalogCheckResult(asset_path=asset.asset_path, exists=True))
    return results


def assert_minio_catalog_ready(
    client: MinioCatalogCheckClient,
    bucket: str,
    assets: list[CatalogSeedAsset],
) -> None:
    results = check_minio_catalog(client, bucket, assets)
    missing = [result for result in results if not result.exists]
    if not missing:
        return

    missing_lines = "\n".join(f"- {result.asset_path}: {result.detail}" for result in missing)
    raise MinioCatalogNotReadyError(
        "MinIO 素材包未就绪，请先上传 Render Catalog 真实素材后再启动后端。\n"
        f"缺失或不可访问素材：\n{missing_lines}"
    )


def generate_placeholder_png(asset: CatalogSeedAsset, width: int = 320, height: int = 240) -> bytes:
    base, accent = _palette(asset.render_key)
    pixels = bytearray()
    for y in range(height):
        for _x in range(width):
            shade = int(18 * y / max(height - 1, 1))
            pixels.extend(_clamp_channel(channel + shade) for channel in base)

    _draw_rounded_product(pixels, width, height, accent)
    _draw_highlight(pixels, width, height)
    return _png_bytes(width, height, bytes(pixels))


def _resolve_payload(
    asset: CatalogSeedAsset,
    *,
    asset_root: Path | None,
    generate_placeholders: bool,
) -> tuple[bytes, str]:
    if asset_root is not None:
        local_path = asset_root / asset.asset_path
        if local_path.is_file():
            return local_path.read_bytes(), str(local_path)

    if generate_placeholders:
        return generate_placeholder_png(asset), "generated-placeholder"

    raise FileNotFoundError(
        f"未找到素材文件：{asset.asset_path}；可提供 --asset-root 或使用 --generate-placeholders"
    )


def _palette(value: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    digest = sha256(value.encode("utf-8")).digest()
    base = (235 + digest[0] % 12, 239 + digest[1] % 10, 232 + digest[2] % 14)
    accent = (70 + digest[3] % 120, 82 + digest[4] % 120, 96 + digest[5] % 120)
    return base, accent


def _draw_rounded_product(
    pixels: bytearray,
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> None:
    center_x = width // 2
    center_y = height // 2
    body_width = width // 3
    body_height = int(height * 0.58)
    left = center_x - body_width // 2
    top = center_y - body_height // 2
    right = left + body_width
    bottom = top + body_height

    for y in range(top, bottom):
        for x in range(left, right):
            radius = min(body_width, body_height) // 5
            if _inside_round_rect(x, y, left, top, right, bottom, radius):
                _set_pixel(pixels, width, x, y, color)

    cap_color = (
        max(color[0] - 35, 0),
        max(color[1] - 35, 0),
        max(color[2] - 35, 0),
    )
    for y in range(top - 18, top + 8):
        for x in range(left + 14, right - 14):
            if 0 <= y < height:
                _set_pixel(pixels, width, x, y, cap_color)


def _draw_highlight(pixels: bytearray, width: int, height: int) -> None:
    for y in range(int(height * 0.28), int(height * 0.72)):
        for x in range(int(width * 0.39), int(width * 0.45)):
            if (x + y) % 9 < 5:
                _set_pixel(pixels, width, x, y, (255, 255, 255))


def _inside_round_rect(
    x: int,
    y: int,
    left: int,
    top: int,
    right: int,
    bottom: int,
    radius: int,
) -> bool:
    if left + radius <= x <= right - radius:
        return True
    if top + radius <= y <= bottom - radius:
        return True
    corner_x = left + radius if x < left + radius else right - radius
    corner_y = top + radius if y < top + radius else bottom - radius
    return (x - corner_x) ** 2 + (y - corner_y) ** 2 <= radius**2


def _set_pixel(
    pixels: bytearray,
    width: int,
    x: int,
    y: int,
    color: tuple[int, int, int],
) -> None:
    index = (y * width + x) * 3
    pixels[index : index + 3] = bytes(color)


def _png_bytes(width: int, height: int, rgb: bytes) -> bytes:
    rows = []
    row_size = width * 3
    for y in range(height):
        rows.append(b"\x00" + rgb[y * row_size : (y + 1) * row_size])
    raw = b"".join(rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type)
    checksum = zlib.crc32(payload, checksum)
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", checksum & 0xFFFFFFFF)
    )


def _clamp_channel(value: int) -> int:
    return max(0, min(value, 255))
