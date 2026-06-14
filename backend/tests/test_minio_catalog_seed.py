import json
from io import BytesIO

from voicecanvas.infrastructure.minio_catalog_seed import (
    CatalogSeedAsset,
    MinioCatalogNotReadyError,
    assert_minio_catalog_ready,
    check_minio_catalog,
    generate_placeholder_png,
    load_catalog_seed_assets,
    seed_minio_catalog,
)


class FakeMinioClient:
    def __init__(self, *, existing: set[str] | None = None, bucket_exists: bool = False) -> None:
        self.bucket_created = False
        self._bucket_exists = bucket_exists
        self._existing = existing or set()
        self.objects: dict[str, tuple[bytes, str]] = {}

    def bucket_exists(self, bucket_name: str) -> bool:
        return self._bucket_exists

    def make_bucket(self, bucket_name: str) -> None:
        self.bucket_created = True

    def stat_object(self, bucket_name: str, object_name: str) -> object:
        if object_name not in self._existing:
            raise RuntimeError("object not found")
        return object()

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BytesIO,
        length: int,
        content_type: str,
    ) -> object:
        payload = data.read()
        assert len(payload) == length
        self.objects[object_name] = (payload, content_type)
        return object()


def test_load_catalog_seed_assets_reads_minio_items(tmp_path) -> None:
    catalog_path = tmp_path / "render-catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "renderKey": "bubble-tea",
                        "displayName": "奶茶",
                        "assetProvider": "minio",
                        "assetPath": "catalog/commerce/food-drink/bubble-tea.png",
                    },
                    {
                        "renderKey": "character",
                        "displayName": "人物",
                        "directRender": True,
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assets = load_catalog_seed_assets(catalog_path)

    assert assets == [
        CatalogSeedAsset(
            render_key="bubble-tea",
            display_name="奶茶",
            asset_path="catalog/commerce/food-drink/bubble-tea.png",
        )
    ]


def test_generate_placeholder_png_returns_valid_png_bytes() -> None:
    payload = generate_placeholder_png(
        CatalogSeedAsset(
            render_key="bubble-tea",
            display_name="奶茶",
            asset_path="catalog/commerce/food-drink/bubble-tea.png",
        )
    )

    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"IHDR" in payload
    assert b"IDAT" in payload


def test_seed_minio_catalog_uploads_generated_placeholders() -> None:
    client = FakeMinioClient()
    asset = CatalogSeedAsset(
        render_key="bubble-tea",
        display_name="奶茶",
        asset_path="catalog/commerce/food-drink/bubble-tea.png",
    )

    results = seed_minio_catalog(
        client,
        "voicecanvas-assets",
        [asset],
        generate_placeholders=True,
    )

    assert client.bucket_created is True
    assert results[0].uploaded is True
    assert results[0].source == "generated-placeholder"
    payload, content_type = client.objects["catalog/commerce/food-drink/bubble-tea.png"]
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert content_type == "image/png"


def test_check_minio_catalog_reports_missing_objects() -> None:
    client = FakeMinioClient(
        bucket_exists=True,
        existing={"catalog/commerce/food-drink/bubble-tea.png"},
    )
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

    results = check_minio_catalog(client, "voicecanvas-assets", assets)

    assert [result.exists for result in results] == [True, False]
    assert results[1].asset_path == "catalog/commerce/digital/smartphone.png"


def test_assert_minio_catalog_ready_fails_when_asset_missing() -> None:
    client = FakeMinioClient(bucket_exists=True)
    asset = CatalogSeedAsset(
        render_key="bubble-tea",
        display_name="奶茶",
        asset_path="catalog/commerce/food-drink/bubble-tea.png",
    )

    try:
        assert_minio_catalog_ready(client, "voicecanvas-assets", [asset])
    except MinioCatalogNotReadyError as error:
        assert "MinIO 素材包未就绪" in str(error)
        assert "catalog/commerce/food-drink/bubble-tea.png" in str(error)
    else:
        raise AssertionError("缺失素材时必须阻止后端启动")
