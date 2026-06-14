from __future__ import annotations

import argparse
import sys
from pathlib import Path

from minio import Minio

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "src"))

from voicecanvas.infrastructure.minio_catalog_seed import (  # noqa: E402
    load_catalog_seed_assets,
    seed_minio_catalog,
)
from voicecanvas.infrastructure.settings import AssetSettings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="将 Render Catalog 素材包初始化到 MinIO。")
    parser.add_argument("--catalog-path", type=Path, default=None, help="render-catalog.json 路径")
    parser.add_argument("--asset-root", type=Path, default=None, help="本地素材根目录")
    parser.add_argument(
        "--generate-placeholders",
        action="store_true",
        help="本地素材缺失时生成可展示 PNG 占位素材",
    )
    parser.add_argument("--dry-run", action="store_true", help="只检查待上传素材，不写入 MinIO")
    args = parser.parse_args()

    settings = AssetSettings.from_env()
    if not settings.minio_endpoint or not settings.minio_bucket:
        raise SystemExit("请先配置 VOICECANVAS_MINIO_ENDPOINT 与 VOICECANVAS_MINIO_BUCKET")
    if not settings.minio_access_key or not settings.minio_secret_key:
        raise SystemExit("请先配置 VOICECANVAS_MINIO_ACCESS_KEY 与 VOICECANVAS_MINIO_SECRET_KEY")

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    assets = load_catalog_seed_assets(args.catalog_path)
    results = seed_minio_catalog(
        client,
        settings.minio_bucket,
        assets,
        asset_root=args.asset_root,
        generate_placeholders=args.generate_placeholders,
        dry_run=args.dry_run,
    )

    action = "检查" if args.dry_run else "上传"
    for result in results:
        print(f"{action}: {result.asset_path} ({result.byte_size} bytes, {result.source})")
    print(f"完成：{len(results)} 个素材")


if __name__ == "__main__":
    main()
