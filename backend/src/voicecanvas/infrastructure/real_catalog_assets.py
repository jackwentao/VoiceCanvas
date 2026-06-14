from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

from voicecanvas.infrastructure.minio_catalog_seed import CatalogSeedAsset

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class RealCatalogAssetSource:
    asset_path: str
    source_url: str
    source_name: str
    license_name: str
    description: str


@dataclass(frozen=True)
class RealCatalogAssetDownload:
    asset_path: str
    target_path: Path
    byte_size: int
    source_url: str
    skipped: bool


REAL_CATALOG_ASSET_SOURCES: dict[str, RealCatalogAssetSource] = {
    "catalog/commerce/food-drink/bubble-tea.png": RealCatalogAssetSource(
        asset_path="catalog/commerce/food-drink/bubble-tea.png",
        source_url="https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/128/emoji_u1f9cb.png",
        source_name="Google Noto Emoji",
        license_name="Apache-2.0",
        description="奶茶主体素材",
    ),
    "catalog/commerce/beauty/skincare-bottle.png": RealCatalogAssetSource(
        asset_path="catalog/commerce/beauty/skincare-bottle.png",
        source_url="https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/128/emoji_u1f9f4.png",
        source_name="Google Noto Emoji",
        license_name="Apache-2.0",
        description="护肤瓶主体素材",
    ),
    "catalog/commerce/digital/smartphone.png": RealCatalogAssetSource(
        asset_path="catalog/commerce/digital/smartphone.png",
        source_url="https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/128/emoji_u1f4f1.png",
        source_name="Google Noto Emoji",
        license_name="Apache-2.0",
        description="手机主体素材",
    ),
    "catalog/commerce/fashion/sneaker.png": RealCatalogAssetSource(
        asset_path="catalog/commerce/fashion/sneaker.png",
        source_url="https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/128/emoji_u1f45f.png",
        source_name="Google Noto Emoji",
        license_name="Apache-2.0",
        description="运动鞋主体素材",
    ),
    "catalog/commerce/home/storage-box.png": RealCatalogAssetSource(
        asset_path="catalog/commerce/home/storage-box.png",
        source_url="https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/128/emoji_u1f4e6.png",
        source_name="Google Noto Emoji",
        license_name="Apache-2.0",
        description="收纳盒主体素材",
    ),
    "catalog/commerce/baby-care/baby-bottle.png": RealCatalogAssetSource(
        asset_path="catalog/commerce/baby-care/baby-bottle.png",
        source_url="https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/128/emoji_u1f37c.png",
        source_name="Google Noto Emoji",
        license_name="Apache-2.0",
        description="奶瓶主体素材",
    ),
    "catalog/commerce/pet/pet-food-bag.png": RealCatalogAssetSource(
        asset_path="catalog/commerce/pet/pet-food-bag.png",
        source_url="https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/128/emoji_u1f9b4.png",
        source_name="Google Noto Emoji",
        license_name="Apache-2.0",
        description="宠物食品主体素材，使用骨头图形表达宠物食品品类",
    ),
    "catalog/commerce/snack/snack-pack.png": RealCatalogAssetSource(
        asset_path="catalog/commerce/snack/snack-pack.png",
        source_url="https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/128/emoji_u1f37f.png",
        source_name="Google Noto Emoji",
        license_name="Apache-2.0",
        description="零食包装主体素材，使用爆米花图形表达零食品类",
    ),
}


def default_real_asset_root() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "real-assets"


def required_real_asset_sources(
    assets: list[CatalogSeedAsset],
) -> list[RealCatalogAssetSource]:
    sources: list[RealCatalogAssetSource] = []
    missing: list[str] = []
    for asset in assets:
        source = REAL_CATALOG_ASSET_SOURCES.get(asset.asset_path)
        if source is None:
            missing.append(asset.asset_path)
            continue
        sources.append(source)

    if missing:
        missing_lines = "\n".join(f"- {path}" for path in missing)
        raise ValueError(f"真实素材下载清单缺少以下 Catalog 路径：\n{missing_lines}")
    return sources


def download_real_catalog_assets(
    asset_root: Path,
    assets: list[CatalogSeedAsset],
    *,
    overwrite: bool = False,
    fetcher: Callable[[str], bytes] | None = None,
) -> list[RealCatalogAssetDownload]:
    download = fetcher or fetch_url
    results: list[RealCatalogAssetDownload] = []

    for source in required_real_asset_sources(assets):
        target_path = asset_root / source.asset_path
        if target_path.is_file() and not overwrite:
            results.append(
                RealCatalogAssetDownload(
                    asset_path=source.asset_path,
                    target_path=target_path,
                    byte_size=target_path.stat().st_size,
                    source_url=source.source_url,
                    skipped=True,
                )
            )
            continue

        payload = download(source.source_url)
        if not payload.startswith(PNG_SIGNATURE):
            raise ValueError(f"下载内容不是 PNG：{source.source_url}")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(payload)
        results.append(
            RealCatalogAssetDownload(
                asset_path=source.asset_path,
                target_path=target_path,
                byte_size=len(payload),
                source_url=source.source_url,
                skipped=False,
            )
        )
    return results


def fetch_url(url: str) -> bytes:
    with urlopen(url, timeout=30) as response:
        return response.read()
