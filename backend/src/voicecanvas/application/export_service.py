import json
from datetime import UTC, datetime
from html import escape
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from voicecanvas.domain.project import CanvasElement, Project, Scene

ExportFormat = Literal["json", "project", "png", "svg"]
ExportScope = Literal["project", "active_scene", "scene"]


class ExportRequest(BaseModel):
    """导出请求的应用层模型，供 API、UI 直连和 LLM 工具调用共同复用。"""

    format: ExportFormat = "json"
    scope: ExportScope = "project"
    scene_id: str | None = Field(default=None, alias="sceneId")

    model_config = {"populate_by_name": True}


class ExportResult(BaseModel):
    """导出产物元数据和可下载内容。"""

    id: str
    project_id: str = Field(alias="projectId")
    format: ExportFormat
    scope: ExportScope
    filename: str
    mime_type: str = Field(alias="mimeType")
    content: str
    byte_size: int = Field(alias="byteSize")
    created_at: str = Field(alias="createdAt")
    scene_id: str | None = Field(default=None, alias="sceneId")

    model_config = {"populate_by_name": True}


class ProjectImportResult(BaseModel):
    project: Project
    imported_at: str = Field(alias="importedAt")

    model_config = {"populate_by_name": True}


class ExportService:
    """统一处理可复现项目包和轻量图片导出。

    图片导出在后端生成 SVG 作为无浏览器环境下的兜底图片；前端按钮仍可用浏览器
    Canvas 把同一 Project State 绘制成 PNG。
    """

    project_bundle_type = "voicecanvas.project"
    schema_version = 1

    def export(self, project: Project, request: ExportRequest) -> ExportResult:
        normalized = self._normalize_request(request)
        if normalized.scope == "project" and normalized.format in {"json", "project"}:
            return self._export_project_bundle(project, normalized)
        return self._export_scene_image(project, normalized)

    def import_project(self, payload: dict[str, Any]) -> ProjectImportResult:
        project_payload = (
            payload.get("project")
            if payload.get("type") == self.project_bundle_type
            else payload
        )
        try:
            project = Project.model_validate(project_payload)
        except ValidationError as error:
            raise ValueError("项目 JSON 格式不正确，无法载入") from error
        return ProjectImportResult(project=project, importedAt=self._now())

    def _normalize_request(self, request: ExportRequest) -> ExportRequest:
        output_format: ExportFormat = "json" if request.format == "project" else request.format
        output_scope = request.scope
        if output_format in {"png", "svg"} and output_scope == "project":
            output_scope = "active_scene"
        return ExportRequest(format=output_format, scope=output_scope, sceneId=request.scene_id)

    def _export_project_bundle(self, project: Project, request: ExportRequest) -> ExportResult:
        created_at = self._now()
        bundle = {
            "type": self.project_bundle_type,
            "schemaVersion": self.schema_version,
            "exportedAt": created_at,
            "project": project.model_dump(by_alias=True),
        }
        content = json.dumps(bundle, ensure_ascii=False, indent=2)
        return ExportResult(
            id=f"export_{uuid4().hex[:12]}",
            projectId=project.id,
            format="json",
            scope=request.scope,
            filename=f"{self._safe_filename(project.title)}.voicecanvas.json",
            mimeType="application/json",
            content=content,
            byteSize=len(content.encode("utf-8")),
            createdAt=created_at,
        )

    def _export_scene_image(self, project: Project, request: ExportRequest) -> ExportResult:
        scene = self._select_scene(project, request)
        created_at = self._now()
        content = self._scene_svg(scene)
        file_format: ExportFormat = "svg" if request.format == "svg" else "png"
        filename_suffix = "svg" if file_format == "svg" else "png"
        return ExportResult(
            id=f"export_{uuid4().hex[:12]}",
            projectId=project.id,
            format=file_format,
            scope=request.scope,
            sceneId=scene.id,
            filename=f"{self._safe_filename(project.title)}-{self._safe_filename(scene.name)}.{filename_suffix}",
            mimeType="image/svg+xml",
            content=content,
            byteSize=len(content.encode("utf-8")),
            createdAt=created_at,
        )

    def _select_scene(self, project: Project, request: ExportRequest) -> Scene:
        scene_id = request.scene_id if request.scope == "scene" else project.active_scene_id
        scene = next((item for item in project.scenes if item.id == scene_id), None)
        if scene is None:
            raise ValueError(f"导出目标镜头不存在：{scene_id}")
        return scene

    def _scene_svg(self, scene: Scene) -> str:
        background = scene.canvas.background.get("color", "#ffffff")
        elements = sorted(scene.elements, key=lambda item: item.z_index)
        body = "\n".join(self._element_svg(element) for element in elements)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{scene.canvas.width:g}" '
            f'height="{scene.canvas.height:g}" '
            f'viewBox="0 0 {scene.canvas.width:g} {scene.canvas.height:g}">'
            f'<rect width="100%" height="100%" fill="{escape(background)}"/>'
            f"{body}</svg>"
        )

    def _element_svg(self, element: CanvasElement) -> str:
        if element.type == "text":
            text = escape(element.text or element.name or "")
            fill = escape(str(element.style.get("color", "#111827")))
            background = element.style.get("backgroundColor")
            font_size = float(element.style.get("fontSize", 28))
            rect = (
                f'<rect x="{element.x:g}" y="{element.y:g}" width="{element.width:g}" '
                f'height="{element.height:g}" rx="8" fill="{escape(str(background))}"/>'
                if background
                else ""
            )
            return (
                f'{rect}<text x="{element.x + 12:g}" '
                f'y="{element.y + element.height / 2 + font_size / 3:g}" '
                f'font-size="{font_size:g}" fill="{fill}" '
                f'font-family="Arial, sans-serif">{text}</text>'
            )

        image_href = self._element_image_href(element)
        if image_href:
            return self._image_svg(element, image_href)

        if element.type in {"shape", "generated_asset", "unknown"}:
            style = element.placeholder_style or element.style or {}
            fill = escape(str(style.get("fill", "#ffffff")))
            stroke = escape(str(style.get("stroke", "#243b53")))
            stroke_width = float(style.get("strokeWidth", style.get("stroke_width", 2)))
            radius = float(style.get("radius", 8))
            label = escape(element.label or element.text or element.name or "")
            text = (
                f'<text x="{element.x + element.width / 2:g}" '
                f'y="{element.y + element.height / 2:g}" '
                f'font-size="24" text-anchor="middle" fill="#111827">{label}</text>'
                if label
                else ""
            )
            return (
                f'<rect x="{element.x:g}" y="{element.y:g}" width="{element.width:g}" '
                f'height="{element.height:g}" rx="{radius:g}" fill="{fill}" '
                f'stroke="{stroke}" stroke-width="{stroke_width:g}"/>{text}'
            )

        if element.type == "image":
            label = escape(
                element.content.get("alt", element.name or "图片")
                if element.content
                else "图片"
            )
            return (
                f'<rect x="{element.x:g}" y="{element.y:g}" width="{element.width:g}" '
                f'height="{element.height:g}" rx="8" fill="#f8fafc" stroke="#94a3b8"/>'
                f'<text x="{element.x + element.width / 2:g}" '
                f'y="{element.y + element.height / 2:g}" '
                f'font-size="20" text-anchor="middle" fill="#334155">{label}</text>'
            )

        return ""

    def _element_image_href(self, element: CanvasElement) -> str | None:
        content = element.content or {}
        if element.type == "image":
            return self._first_string(
                content.get("url"),
                (element.image or {}).get("url"),
            )

        if element.type == "generated_asset" and (element.asset or {}).get("status") == "ready":
            return self._first_string(
                content.get("url"),
                (element.asset or {}).get("url"),
                (element.image or {}).get("url"),
            )

        return None

    def _image_svg(self, element: CanvasElement, href: str) -> str:
        radius = float(element.style.get("radius", element.style.get("borderRadius", 8)))
        clip_id = f"clip-{self._safe_svg_id(element.id)}"
        safe_href = escape(href, quote=True)
        return (
            f'<defs><clipPath id="{clip_id}">'
            f'<rect x="{element.x:g}" y="{element.y:g}" width="{element.width:g}" '
            f'height="{element.height:g}" rx="{radius:g}"/></clipPath></defs>'
            f'<image href="{safe_href}" xlink:href="{safe_href}" x="{element.x:g}" '
            f'y="{element.y:g}" width="{element.width:g}" height="{element.height:g}" '
            f'preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip_id})"/>'
        )

    def _first_string(self, *values: Any) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value
        return None

    def _safe_svg_id(self, value: str) -> str:
        safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in value)
        return safe.strip("-") or "image"

    def _safe_filename(self, value: str) -> str:
        safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.strip())
        return safe.strip("-") or "voicecanvas"

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
