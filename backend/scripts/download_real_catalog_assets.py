from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "src"))

from voicecanvas.infrastructure.minio_catalog_seed import load_catalog_seed_assets  # noqa: E402
from voicecanvas.infrastructure.real_catalog_assets import (  # noqa: E402
    REAL_CATALOG_ASSET_SOURCES,
    default_real_asset_root,
    download_real_catalog_assets,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="下载 Render Catalog 真实素材包到本地目录。")
    parser.add_argument("--catalog-path", type=Path, default=None, help="render-catalog.json 路径")
    parser.add_argument(
        "--asset-root",
        type=Path,
        default=default_real_asset_root(),
        help="真实素材下载目录，默认 backend/data/real-assets",
    )
    parser.add_argument("--overwrite", action="store_true", help="覆盖已经存在的本地素材")
    args = parser.parse_args()

    assets = load_catalog_seed_assets(args.catalog_path)
    results = download_real_catalog_assets(
        args.asset_root,
        assets,
        overwrite=args.overwrite,
    )

    for result in results:
        action = "跳过" if result.skipped else "下载"
        print(f"{action}: {result.asset_path} ({result.byte_size} bytes) -> {result.target_path}")

    source_names = {
        f"{source.source_name} / {source.license_name}"
        for source in REAL_CATALOG_ASSET_SOURCES.values()
    }
    print(f"完成：{len(results)} 个真实素材")
    print(f"素材来源：{'; '.join(sorted(source_names))}")


if __name__ == "__main__":
    main()
