from voicecanvas.infrastructure.minio_catalog_seed import CatalogSeedAsset
from voicecanvas.infrastructure.real_catalog_assets import (
    PNG_SIGNATURE,
    download_real_catalog_assets,
    required_real_asset_sources,
)


def test_real_asset_sources_cover_catalog_assets() -> None:
    assets = [
        CatalogSeedAsset(
            render_key="bubble-tea",
            display_name="奶茶",
            asset_path="catalog/commerce/food-drink/bubble-tea.png",
        ),
        CatalogSeedAsset(
            render_key="smartphone",
            display_name="手机",
            asset_path="catalog/commerce/digital/smartphone.png",
        ),
    ]

    sources = required_real_asset_sources(assets)

    assert [source.asset_path for source in sources] == [
        "catalog/commerce/food-drink/bubble-tea.png",
        "catalog/commerce/digital/smartphone.png",
    ]
    assert all(source.license_name for source in sources)


def test_download_real_catalog_assets_writes_png_files(tmp_path) -> None:
    asset = CatalogSeedAsset(
        render_key="bubble-tea",
        display_name="奶茶",
        asset_path="catalog/commerce/food-drink/bubble-tea.png",
    )

    results = download_real_catalog_assets(
        tmp_path,
        [asset],
        fetcher=lambda url: PNG_SIGNATURE + b"fake-png",
    )

    target_path = tmp_path / "catalog/commerce/food-drink/bubble-tea.png"
    assert results[0].skipped is False
    assert results[0].target_path == target_path
    assert target_path.read_bytes().startswith(PNG_SIGNATURE)


def test_download_real_catalog_assets_skips_existing_files(tmp_path) -> None:
    asset = CatalogSeedAsset(
        render_key="bubble-tea",
        display_name="奶茶",
        asset_path="catalog/commerce/food-drink/bubble-tea.png",
    )
    target_path = tmp_path / asset.asset_path
    target_path.parent.mkdir(parents=True)
    target_path.write_bytes(PNG_SIGNATURE + b"existing")

    results = download_real_catalog_assets(
        tmp_path,
        [asset],
        fetcher=lambda url: PNG_SIGNATURE + b"new",
    )

    assert results[0].skipped is True
    assert target_path.read_bytes() == PNG_SIGNATURE + b"existing"
