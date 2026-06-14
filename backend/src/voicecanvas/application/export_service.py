import json
from collections.abc import Callable
from datetime import UTC, datetime
from html import escape
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from voicecanvas.application.asset_storage import catalog_proxy_url
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
    illustration_svg_styles = """
.object-illustration{overflow:visible}
.character-shadow,.cat-shadow,.table-shadow{fill:rgba(27,43,52,.12)}
.character-hair-back,.character-hair-front{fill:#3b2417;stroke:#25150d;stroke-width:5;stroke-linejoin:round}
.character-face,.character-neck{fill:#ffd2ad;stroke:#8a4b2a;stroke-width:4}
.character-eye,.cat-eye,.cat-nose{fill:#1b2b34}
.character-smile,.character-arm,.character-leg,.character-shoe{fill:none;stroke:#8a4b2a;stroke-width:5;stroke-linecap:round;stroke-linejoin:round}
.character-dress{fill:#f15b8a;stroke:#8b2450;stroke-width:5;stroke-linejoin:round}
.character-shirt{fill:#2d6cdf;stroke:#173f8a;stroke-width:5;stroke-linejoin:round}
.character-pants{fill:#243b53;stroke:#1b2b34;stroke-width:5;stroke-linejoin:round}
.character-illustration.is-neutral .character-shirt{fill:#1f8a5b;stroke:#176146}
.character-illustration.is-neutral .character-hair-back{fill:#5a3825}
.character-illustration.is-neutral .character-hair-front{fill:#5a3825}
.cat-body,.cat-head,.cat-ear{fill:#f6b25f;stroke:#7c3f15;stroke-width:5;stroke-linejoin:round}
.cat-tail,.cat-mouth,.cat-whisker,.cat-leg{fill:none;stroke:#7c3f15;stroke-width:5;stroke-linecap:round}
.table-top{fill:#9a5424;stroke:#5d2d12;stroke-width:5;stroke-linejoin:round}
.table-front,.table-leg{fill:#7d3f18;stroke:#5d2d12;stroke-width:5;stroke-linejoin:round}
.table-grain{fill:none;stroke:#d7a46c;stroke-width:5;stroke-linecap:round;opacity:.8}
.table-object{fill:#f6c453;stroke:#b7791f;stroke-width:4}
""".strip()

    def __init__(self, catalog_url_resolver: Callable[[str], str] | None = None) -> None:
        self._catalog_url_resolver = catalog_url_resolver or catalog_proxy_url

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
        layout_index = self._layout_index(scene)
        rendered = [self._element_svg(element, layout_index) for element in elements]
        body = "\n".join(rendered)
        styles = (
            f"<style>{self.illustration_svg_styles}</style>"
            if any("object-illustration" in item for item in rendered)
            else ""
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{scene.canvas.width:g}" '
            f'height="{scene.canvas.height:g}" '
            f'viewBox="0 0 {scene.canvas.width:g} {scene.canvas.height:g}">'
            f'<rect width="100%" height="100%" fill="{escape(background)}"/>'
            f"{styles}{body}</svg>"
        )

    def _element_svg(
        self,
        element: CanvasElement,
        layout_index: dict[str, tuple[float, float, float, float]],
    ) -> str:
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

        if element.type == "connector":
            return self._connector_svg(element, layout_index)

        image_href = self._element_image_href(element)
        if image_href:
            return self._image_svg(element, image_href)

        illustration = self._illustration_svg(element)
        if illustration:
            return illustration

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
                self._catalog_href(element),
            )

        if element.type == "generated_asset":
            return self._catalog_href(element)

        return None

    def _catalog_href(self, element: CanvasElement) -> str | None:
        asset_path = (element.metadata or {}).get("assetPath")
        if not isinstance(asset_path, str) or not asset_path.strip():
            return None
        return self._catalog_url_resolver(asset_path)

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

    def _illustration_svg(self, element: CanvasElement) -> str:
        spec = self._semantic_spec(element)
        if spec is None:
            return ""
        label = self._first_string(
            (element.content or {}).get("label"),
            (element.content or {}).get("alt"),
            element.label,
            element.name,
        ) or ""
        svg = self._render_illustration_svg(spec["kind"], label, spec.get("variant", "neutral"))
        if not svg:
            return ""
        sized_svg = svg.replace(
            "<svg ",
            f'<svg width="{element.width:g}" height="{element.height:g}" ',
            1,
        )
        return (
            f'<g transform="translate({element.x:g} {element.y:g})">'
            f"{sized_svg}</g>"
        )

    def _semantic_spec(self, element: CanvasElement) -> dict[str, str] | None:
        metadata = element.metadata or {}
        render_key = metadata.get("renderKey") or metadata.get("renderHint")
        if render_key == "girl":
            return {"kind": "character", "variant": "female"}
        if render_key in {"character", "cat", "table"}:
            return {
                "kind": str(render_key),
                "variant": self._normalize_character_variant(metadata.get("renderVariant")),
            }

        subject_spec = self._semantic_spec_from_subject(element.subject)
        if subject_spec is not None:
            return subject_spec

        tags = element.semantic.get("tags", []) if isinstance(element.semantic, dict) else []
        text = " ".join(
            str(value)
            for value in (
                element.name,
                element.text,
                element.label,
                (element.content or {}).get("label"),
                (element.content or {}).get("alt"),
                (element.asset or {}).get("kind"),
                *tags,
            )
            if value
        )
        return self._semantic_spec_from_text(text)

    def _semantic_spec_from_subject(self, subject: dict[str, Any] | None) -> dict[str, str] | None:
        if not isinstance(subject, dict):
            return None
        for value in subject.values():
            if not isinstance(value, dict):
                continue
            render_key = value.get("renderKey")
            if render_key in {"character", "cat", "table"}:
                return {
                    "kind": str(render_key),
                    "variant": self._normalize_character_variant(
                        value.get("variant") or value.get("gender")
                    ),
                }
            text = " ".join(
                str(item)
                for item in (
                    value.get("category"),
                    value.get("role"),
                    value.get("gender"),
                    value.get("variant"),
                    *(value.get("keyFeatures") or []),
                )
                if item
            )
            text_spec = self._semantic_spec_from_text(text)
            if text_spec is not None:
                return text_spec
        return None

    def _semantic_spec_from_text(self, text: str) -> dict[str, str] | None:
        normalized = text.lower()
        if self._contains_any(normalized, ("男生", "男孩", "男人", "男性", "boy", "man")):
            return {"kind": "character", "variant": "male"}
        if self._contains_any(normalized, ("女生", "女孩", "女人", "女性", "girl", "woman")):
            return {"kind": "character", "variant": "female"}
        if self._contains_any(normalized, ("人物", "人像", "person", "character")):
            return {"kind": "character", "variant": "neutral"}
        if self._contains_any(normalized, ("猫", "小猫", "cat")):
            return {"kind": "cat", "variant": ""}
        if self._contains_any(normalized, ("桌", "桌子", "table", "desk")):
            return {"kind": "table", "variant": ""}
        return None

    def _render_illustration_svg(self, kind: str, label: str, variant: str = "neutral") -> str:
        if kind == "character":
            return self._character_illustration_svg(label, variant)
        if kind == "cat":
            return self._cat_illustration_svg(label)
        if kind == "table":
            return self._table_illustration_svg(label)
        return ""

    def _character_illustration_svg(self, label: str, variant: str) -> str:
        normalized = self._normalize_character_variant(variant)
        is_female = normalized == "female"
        hair_back = (
            "M61 85 C56 41 82 18 111 18 C146 18 166 45 159 91 C155 119 66 118 61 85 Z"
            if is_female
            else "M70 67 C73 35 91 21 111 21 C139 21 153 40 150 70 C130 53 94 51 70 67 Z"
        )
        hair_front = (
            "M73 64 C83 34 121 25 148 55 C130 50 113 48 92 61 C85 66 79 68 73 64 Z"
            if is_female
            else "M73 61 C89 35 125 34 149 59 C130 55 105 54 83 68 Z"
        )
        body = (
            '<path class="character-dress" d="M84 128 H136 L154 190 H66 Z"></path>'
            if is_female
            else (
                '<path class="character-shirt" d="M78 128 H142 L150 188 H70 Z"></path>'
                '<path class="character-pants" '
                'd="M86 188 H134 L128 211 H114 L110 195 L106 211 H92 Z"></path>'
            )
        )
        legs = (
            '<path class="character-leg" d="M94 190 L88 211 M126 190 L132 211"></path>'
            if is_female
            else ""
        )
        safe_label = escape(label or "人物", quote=True)
        return "".join(
            [
                f'<svg class="object-illustration character-illustration is-{normalized}" ',
                f'viewBox="0 0 220 220" role="img" aria-label="{safe_label}">',
                '<ellipse class="character-shadow" cx="110" cy="198" rx="56" ry="10"></ellipse>',
                f'<path class="character-hair-back" d="{hair_back}"></path>',
                '<circle class="character-face" cx="110" cy="75" r="39"></circle>',
                f'<path class="character-hair-front" d="{hair_front}"></path>',
                '<circle class="character-eye" cx="97" cy="78" r="4"></circle>',
                '<circle class="character-eye" cx="123" cy="78" r="4"></circle>',
                '<path class="character-smile" d="M99 93 C106 101 117 101 124 93"></path>',
                '<path class="character-neck" d="M101 112 H119 L123 130 H97 Z"></path>',
                body,
                '<path class="character-arm" ',
                'd="M84 137 C61 148 56 165 66 177 M136 137 C160 148 165 165 154 177">',
                "</path>",
                legs,
                '<path class="character-shoe" d="M78 211 H94 M126 211 H142"></path>',
                "</svg>",
            ]
        )

    def _cat_illustration_svg(self, label: str) -> str:
        safe_label = escape(label or "猫", quote=True)
        return "".join(
            [
                '<svg class="object-illustration cat-illustration" ',
                f'viewBox="0 0 240 180" role="img" aria-label="{safe_label}">',
                '<ellipse class="cat-shadow" cx="126" cy="154" rx="78" ry="12"></ellipse>',
                '<path class="cat-tail" ',
                'd="M178 116 C218 92 216 48 181 54 C163 57 163 83 181 84"></path>',
                '<ellipse class="cat-body" cx="124" cy="112" rx="58" ry="42"></ellipse>',
                '<circle class="cat-head" cx="92" cy="74" r="38"></circle>',
                '<path class="cat-ear" d="M63 49 L66 12 L91 42 Z"></path>',
                '<path class="cat-ear" d="M100 41 L129 16 L127 54 Z"></path>',
                '<circle class="cat-eye" cx="80" cy="72" r="4"></circle>',
                '<circle class="cat-eye" cx="104" cy="72" r="4"></circle>',
                '<path class="cat-nose" d="M90 82 L96 82 L93 87 Z"></path>',
                '<path class="cat-mouth" ',
                'd="M93 88 C88 94 80 94 76 90 M93 88 C98 94 106 94 110 90">',
                "</path>",
                '<path class="cat-whisker" ',
                'd="M60 79 L22 70 M61 88 L23 91 M124 79 L160 68 M123 88 L160 92">',
                "</path>",
                '<path class="cat-leg" ',
                'd="M91 142 L87 164 M123 146 L123 166 M153 142 L159 164"></path>',
                "</svg>",
            ]
        )

    def _table_illustration_svg(self, label: str) -> str:
        safe_label = escape(label or "桌子", quote=True)
        return "".join(
            [
                '<svg class="object-illustration table-illustration" ',
                f'viewBox="0 0 260 180" role="img" aria-label="{safe_label}">',
                '<ellipse class="table-shadow" cx="132" cy="160" rx="92" ry="10"></ellipse>',
                '<path class="table-top" ',
                'd="M42 55 C44 43 55 36 70 36 H190 C207 36 218 44 220 58 L228 92 H34 Z">',
                "</path>",
                '<path class="table-front" d="M34 92 H228 L213 112 H49 Z"></path>',
                '<path class="table-leg" d="M63 109 H83 L76 158 H55 Z"></path>',
                '<path class="table-leg" d="M177 109 H198 L207 158 H186 Z"></path>',
                '<path class="table-grain" d="M66 62 H195 M74 78 H184"></path>',
                '<rect class="table-object" x="112" y="18" width="38" height="32" rx="8"></rect>',
                "</svg>",
            ]
        )

    def _connector_svg(
        self,
        element: CanvasElement,
        layout_index: dict[str, tuple[float, float, float, float]],
    ) -> str:
        from_point = self._resolve_endpoint(element.from_anchor, element.to_anchor, layout_index)
        to_point = self._resolve_endpoint(element.to_anchor, element.from_anchor, layout_index)
        if from_point is None or to_point is None:
            return ""

        stroke = self._connector_stroke(element)
        marker_id = f"arrow-{self._safe_svg_id(element.id)}"
        marker = (
            f'<defs><marker id="{marker_id}" markerWidth="8" markerHeight="8" '
            f'refX="7" refY="4" orient="auto" markerUnits="strokeWidth">'
            f'<path d="M0,0 L8,4 L0,8 Z" fill="{escape(stroke["color"])}"/></marker></defs>'
            if self._connector_marker_end(element)
            else ""
        )
        marker_end = (
            f' marker-end="url(#{marker_id})"'
            if self._connector_marker_end(element)
            else ""
        )
        dash = (
            f' stroke-dasharray="{" ".join(str(item) for item in stroke["dash"])}"'
            if isinstance(stroke.get("dash"), list)
            else ""
        )
        path = self._connector_path(from_point, to_point, element.connector or {})
        label_point = self._connector_label_point(from_point, to_point)
        label = escape(element.text or (element.content or {}).get("label", "") or "")
        description = escape(element.description or "")
        label_svg = (
            f'<text x="{label_point[0]:g}" y="{label_point[1]:g}" text-anchor="middle" '
            f'font-size="18" font-weight="800" fill="{escape(stroke["color"])}" '
            f'stroke="#ffffff" stroke-width="4" paint-order="stroke">{label}</text>'
            if label
            else ""
        )
        description_svg = (
            f'<text x="{label_point[0]:g}" y="{label_point[1] + 20:g}" text-anchor="middle" '
            f'font-size="14" font-weight="700" fill="#244236" stroke="#ffffff" '
            f'stroke-width="3" paint-order="stroke">{description}</text>'
            if description
            else ""
        )
        return (
            f'{marker}<path d="{path}" fill="none" stroke="{escape(stroke["color"])}" '
            f'stroke-width="{stroke["width"]:g}" stroke-linecap="round" '
            f'stroke-linejoin="round"{dash}{marker_end}/>{label_svg}{description_svg}'
        )

    def _layout_index(self, scene: Scene) -> dict[str, tuple[float, float, float, float]]:
        return {
            element.id: (element.x, element.y, element.width, element.height)
            for element in scene.elements
        }

    def _resolve_endpoint(
        self,
        endpoint: Any,
        opposite_endpoint: Any,
        layout_index: dict[str, tuple[float, float, float, float]],
    ) -> tuple[float, float] | None:
        if endpoint is None:
            return None
        target = endpoint.target if hasattr(endpoint, "target") else endpoint.get("target")
        element_id = None
        if isinstance(target, dict) and target.get("type") == "element":
            element_id = target.get("elementId")
        if element_id is None:
            element_id = getattr(endpoint, "element_id", None) or endpoint.get("elementId")
        if not isinstance(element_id, str) or element_id not in layout_index:
            return None

        anchor = getattr(endpoint, "anchor", None) or endpoint.get("anchor") or "auto"
        opposite = self._resolve_endpoint_center(opposite_endpoint, layout_index)
        return self._anchor_point(layout_index[element_id], anchor, opposite)

    def _resolve_endpoint_center(
        self,
        endpoint: Any,
        layout_index: dict[str, tuple[float, float, float, float]],
    ) -> tuple[float, float] | None:
        if endpoint is None:
            return None
        target = endpoint.target if hasattr(endpoint, "target") else endpoint.get("target")
        element_id = None
        if isinstance(target, dict) and target.get("type") == "element":
            element_id = target.get("elementId")
        if element_id is None:
            element_id = getattr(endpoint, "element_id", None) or endpoint.get("elementId")
        if not isinstance(element_id, str) or element_id not in layout_index:
            return None
        x, y, width, height = layout_index[element_id]
        return (x + width / 2, y + height / 2)

    def _anchor_point(
        self,
        bounds: tuple[float, float, float, float],
        anchor: Any,
        opposite: tuple[float, float] | None,
    ) -> tuple[float, float]:
        x, y, width, height = bounds
        normalized = self._normalize_anchor(bounds, anchor, opposite)
        if isinstance(normalized, dict):
            ratio = min(1, max(0, float(normalized.get("ratio", 0.5))))
            side = normalized.get("side")
            if side == "top":
                return (x + width * ratio, y)
            if side == "right":
                return (x + width, y + height * ratio)
            if side == "bottom":
                return (x + width * ratio, y + height)
            return (x, y + height * ratio)
        if normalized == "top":
            return (x + width / 2, y)
        if normalized == "right":
            return (x + width, y + height / 2)
        if normalized == "bottom":
            return (x + width / 2, y + height)
        if normalized == "left":
            return (x, y + height / 2)
        return (x + width / 2, y + height / 2)

    def _normalize_anchor(
        self,
        bounds: tuple[float, float, float, float],
        anchor: Any,
        opposite: tuple[float, float] | None,
    ) -> Any:
        if anchor != "auto" or opposite is None:
            return anchor
        x, y, width, height = bounds
        center = (x + width / 2, y + height / 2)
        dx = opposite[0] - center[0]
        dy = opposite[1] - center[1]
        if abs(dx) >= abs(dy):
            return "right" if dx >= 0 else "left"
        return "bottom" if dy >= 0 else "top"

    def _connector_path(
        self,
        from_point: tuple[float, float],
        to_point: tuple[float, float],
        connector: dict[str, Any],
    ) -> str:
        routing = connector.get("routing") or (
            "bezier" if connector.get("kind") == "curve" else "straight"
        )
        if routing == "bezier" or connector.get("kind") == "curve":
            delta = max(48, abs(to_point[0] - from_point[0]) * 0.36)
            return (
                f"M {from_point[0]:g} {from_point[1]:g} "
                f"C {from_point[0] + delta:g} {from_point[1]:g}, "
                f"{to_point[0] - delta:g} {to_point[1]:g}, {to_point[0]:g} {to_point[1]:g}"
            )
        if routing == "orthogonal" or connector.get("kind") == "elbow":
            mid_x = (from_point[0] + to_point[0]) / 2
            return (
                f"M {from_point[0]:g} {from_point[1]:g} L {mid_x:g} {from_point[1]:g} "
                f"L {mid_x:g} {to_point[1]:g} L {to_point[0]:g} {to_point[1]:g}"
            )
        return f"M {from_point[0]:g} {from_point[1]:g} L {to_point[0]:g} {to_point[1]:g}"

    def _connector_label_point(
        self,
        from_point: tuple[float, float],
        to_point: tuple[float, float],
    ) -> tuple[float, float]:
        return ((from_point[0] + to_point[0]) / 2, (from_point[1] + to_point[1]) / 2 - 12)

    def _connector_stroke(self, element: CanvasElement) -> dict[str, Any]:
        stroke = element.style.get("stroke")
        if isinstance(stroke, str):
            return {
                "color": stroke,
                "width": float(element.style.get("strokeWidth", 1)),
                "dash": None,
            }
        if isinstance(stroke, dict):
            return {
                "color": str(stroke.get("color", "#f15b4a")),
                "width": float(stroke.get("width", element.style.get("strokeWidth", 1))),
                "dash": stroke.get("dash"),
            }
        return {
            "color": "#f15b4a",
            "width": float(element.style.get("strokeWidth", 1)),
            "dash": None,
        }

    def _connector_marker_end(self, element: CanvasElement) -> bool:
        marker_end = element.style.get("markerEnd")
        if isinstance(marker_end, dict) and marker_end.get("type") == "none":
            return False
        return element.style.get("arrowEnd", True) is not False

    def _first_string(self, *values: Any) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value
        return None

    def _normalize_character_variant(self, value: Any) -> str:
        if value in {"male", "男", "男生", "男性"}:
            return "male"
        if value in {"female", "女", "女生", "女性"}:
            return "female"
        return "neutral"

    def _contains_any(self, value: str, needles: tuple[str, ...]) -> bool:
        return any(needle in value for needle in needles)

    def _safe_svg_id(self, value: str) -> str:
        safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in value)
        return safe.strip("-") or "image"

    def _safe_filename(self, value: str) -> str:
        safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.strip())
        return safe.strip("-") or "voicecanvas"

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
