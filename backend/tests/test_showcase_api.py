"""画廊分类、素材白名单与业务状态隔离测试。"""

from xml.etree import ElementTree

from fastapi import FastAPI
from fastapi.testclient import TestClient

from voicecanvas.api.showcase import showcase_router


def client() -> TestClient:
    app = FastAPI()
    app.include_router(showcase_router())
    return TestClient(app)


def test_gallery_contains_original_artwork_and_server_categories():
    api = client()
    response = api.get("/api/showcase")
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["total"] == 6
    assert len({item["id"] for item in catalog["items"]}) == 6
    assert {item.get("hero") for item in catalog["items"]} >= {"main", "front", "back"}
    categories = {item["id"] for item in catalog["categories"]}
    for item in catalog["items"]:
        assert item["category"] in categories
        assert "projectId" not in item
        artwork = api.get(item["imageUrl"])
        assert artwork.status_code == 200
        assert artwork.headers["content-type"].startswith("image/svg+xml")
        svg = ElementTree.fromstring(artwork.content)
        assert svg.attrib["viewBox"] == "0 0 800 600"
        assert not list(svg.iter("{http://www.w3.org/2000/svg}script"))
        assert item["title"] in artwork.text


def test_gallery_filters_on_server_and_rejects_unknown_categories_and_artworks():
    api = client()
    all_items = api.get("/api/showcase").json()["items"]
    filtered = api.get("/api/showcase?category=story").json()
    assert filtered["items"] == [item for item in all_items if item["category"] == "story"]
    assert filtered["total"] == 1
    assert api.get("/api/showcase?category=unknown").status_code == 404
    for artwork_id in ["unknown", "catalog.json", "%2E%2E%2Fcatalog"]:
        assert api.get(f"/api/showcase/{artwork_id}/artwork").status_code == 404
