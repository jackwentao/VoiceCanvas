from __future__ import annotations

import argparse
import sys
from pathlib import Path

from minio import Minio

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "src"))

from voicecanvas.infrastructure.minio_catalog_seed import (  # noqa: E402
    assert_minio_catalog_ready,
    check_minio_catalog,
    load_catalog_seed_assets,
)
from voicecanvas.infrastructure.settings import AssetSettings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="检查 Render Catalog 素材包是否已完整上传到 MinIO。"
    )
    parser.add_argument("--catalog-path", type=Path, default=None, help="render-catalog.json 路径")
    parser.add_argument("--strict", action="store_true", help="缺失任意素材时返回非 0 状态")
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

    if args.strict:
        assert_minio_catalog_ready(client, settings.minio_bucket, assets)

    results = check_minio_catalog(client, settings.minio_bucket, assets)
    for result in results:
        status = "存在" if result.exists else "缺失"
        detail = f"；{result.detail}" if result.detail else ""
        print(f"{status}: {result.asset_path}{detail}")

    ready_count = sum(1 for result in results if result.exists)
    print(f"完成：{ready_count}/{len(results)} 个素材已上传")


if __name__ == "__main__":
    main()
