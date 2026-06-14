import json

from voicecanvas.application.export_service import ExportRequest, ExportService
from voicecanvas.application.project_repository import InMemoryProjectRepository
from voicecanvas.domain.project import Project


def test_export_project_bundle_can_be_imported_again() -> None:
    repository = InMemoryProjectRepository()
    project = repository.get_or_create("project_export")
    service = ExportService()

    result = service.export(project, ExportRequest(format="json", scope="project"))
    payload = json.loads(result.content)
    imported = service.import_project(payload)

    assert result.filename.endswith(".voicecanvas.json")
    assert payload["type"] == "voicecanvas.project"
    assert payload["project"]["id"] == "project_export"
    assert imported.project == project


def test_import_rejects_non_project_json() -> None:
    service = ExportService()

    try:
        service.import_project({"hello": "world"})
    except ValueError as error:
        assert "项目 JSON 格式不正确" in str(error)
    else:
        raise AssertionError("非项目 JSON 必须载入失败")


def test_export_active_scene_image_returns_svg_source() -> None:
    project = InMemoryProjectRepository().get_or_create("project_image")
    service = ExportService()

    result = service.export(project, ExportRequest(format="png", scope="active_scene"))

    assert result.format == "png"
    assert result.mime_type == "image/svg+xml"
    assert result.scene_id == project.active_scene_id
    assert result.filename.endswith(".png")
    assert result.content.startswith("<svg")
    assert "rect" in result.content


def test_export_scene_image_embeds_real_asset_urls() -> None:
    project = Project.model_validate(
        {
            "id": "project_asset_export",
            "title": "素材导出测试",
            "mode": "storyboard",
            "activeSceneId": "scene_asset_export",
            "scenes": [
                {
                    "id": "scene_asset_export",
                    "name": "主画面",
                    "order": 1,
                    "canvas": {"width": 400, "height": 240, "background": {"color": "#ffffff"}},
                    "elements": [
                        {
                            "id": "el_image",
                            "type": "image",
                            "name": "照片",
                            "x": 12,
                            "y": 16,
                            "width": 96,
                            "height": 80,
                            "zIndex": 1,
                            "content": {
                                "url": "https://cdn.example.test/photo.png",
                                "alt": "照片",
                            },
                        },
                        {
                            "id": "el_ready_asset",
                            "type": "generated_asset",
                            "name": "小女孩",
                            "x": 132,
                            "y": 16,
                            "width": 96,
                            "height": 120,
                            "zIndex": 2,
                            "content": {
                                "url": "https://cdn.example.test/girl.png",
                                "alt": "小女孩",
                            },
                            "asset": {"kind": "character", "status": "ready"},
                        },
                    ],
                }
            ],
        }
    )
    service = ExportService()

    result = service.export(project, ExportRequest(format="png", scope="active_scene"))

    assert '<image href="https://cdn.example.test/photo.png"' in result.content
    assert '<image href="https://cdn.example.test/girl.png"' in result.content
    assert ">小女孩</text>" not in result.content


def test_export_scene_image_renders_catalog_asset_semantic_character_and_connector() -> None:
    project = Project.model_validate(
        {
            "id": "project_semantic_export",
            "title": "语义导出测试",
            "mode": "storyboard",
            "activeSceneId": "scene_semantic_export",
            "scenes": [
                {
                    "id": "scene_semantic_export",
                    "name": "主画面",
                    "order": 1,
                    "canvas": {"width": 640, "height": 360, "background": {"color": "#ffffff"}},
                    "elements": [
                        {
                            "id": "el_bubble_tea",
                            "type": "generated_asset",
                            "name": "珍珠奶茶",
                            "x": 120,
                            "y": 96,
                            "width": 120,
                            "height": 140,
                            "zIndex": 1,
                            "content": {"alt": "珍珠奶茶"},
                            "asset": {"kind": "product", "status": "pending"},
                            "metadata": {
                                "renderKey": "bubble-tea",
                                "assetPath": "catalog/commerce/food-drink/bubble-tea.png",
                            },
                            "placeholderStyle": {
                                "fill": "#ffffff",
                                "stroke": "#1f8a5b",
                                "strokeWidth": 2,
                            },
                        },
                        {
                            "id": "el_girl",
                            "type": "generated_asset",
                            "name": "小女孩",
                            "x": 320,
                            "y": 76,
                            "width": 110,
                            "height": 150,
                            "zIndex": 2,
                            "content": {"alt": "小女孩"},
                            "asset": {"kind": "character", "status": "pending"},
                            "metadata": {"renderKey": "character", "renderVariant": "female"},
                            "subject": {"character": {"gender": "女性", "renderKey": "character"}},
                            "placeholderStyle": {
                                "fill": "#ffffff",
                                "stroke": "#243b53",
                                "strokeWidth": 2,
                            },
                        },
                        {
                            "id": "el_arrow",
                            "type": "connector",
                            "name": "推荐箭头",
                            "x": 0,
                            "y": 0,
                            "width": 1,
                            "height": 1,
                            "zIndex": 3,
                            "connector": {
                                "kind": "line",
                                "from": {
                                    "target": {"type": "element", "elementId": "el_girl"},
                                    "anchor": "left",
                                },
                                "to": {
                                    "target": {"type": "element", "elementId": "el_bubble_tea"},
                                    "anchor": "right",
                                },
                                "routing": "straight",
                            },
                            "content": {"label": "推荐"},
                            "style": {"stroke": "#f15b4a", "strokeWidth": 4, "arrowEnd": True},
                        },
                    ],
                }
            ],
        }
    )
    service = ExportService(catalog_url_resolver=lambda path: f"/assets/{path}")

    result = service.export(project, ExportRequest(format="png", scope="active_scene"))

    assert '<image href="/assets/catalog/commerce/food-drink/bubble-tea.png"' in result.content
    assert "character-illustration is-female" in result.content
    assert ">小女孩</text>" not in result.content
    assert '<path d="M ' in result.content
    assert "marker-end" in result.content
    assert ">推荐</text>" in result.content


def test_export_specific_scene_rejects_missing_scene() -> None:
    project = InMemoryProjectRepository().get_or_create("project_missing_scene")
    service = ExportService()

    try:
        service.export(project, ExportRequest(format="png", scope="scene", sceneId="missing"))
    except ValueError as error:
        assert "导出目标镜头不存在" in str(error)
    else:
        raise AssertionError("缺失镜头必须导出失败")
