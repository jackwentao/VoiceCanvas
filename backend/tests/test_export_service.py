import json

from voicecanvas.application.export_service import ExportRequest, ExportService
from voicecanvas.application.project_repository import InMemoryProjectRepository


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


def test_export_specific_scene_rejects_missing_scene() -> None:
    project = InMemoryProjectRepository().get_or_create("project_missing_scene")
    service = ExportService()

    try:
        service.export(project, ExportRequest(format="png", scope="scene", sceneId="missing"))
    except ValueError as error:
        assert "导出目标镜头不存在" in str(error)
    else:
        raise AssertionError("缺失镜头必须导出失败")
