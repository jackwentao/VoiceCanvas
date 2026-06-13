from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, PositiveFloat, field_validator, model_validator


class ElementType(StrEnum):
    TEXT = "text"
    SHAPE = "shape"
    IMAGE = "image"
    GENERATED_ASSET = "generated_asset"
    CONNECTOR = "connector"
    GROUP = "group"
    UNKNOWN = "unknown"


class ElementTransform(BaseModel):
    x: float
    y: float
    width: PositiveFloat
    height: PositiveFloat
    rotation: float | None = None
    opacity: float | None = None
    visible: bool | None = None
    locked: bool | None = None

    @field_validator("x", "y", "rotation", "opacity")
    @classmethod
    def number_must_be_finite(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("坐标与数值属性必须是有限数字")
        return value


class ElementLayer(BaseModel):
    z_index: int = Field(alias="zIndex")
    blend_mode: Literal["normal", "multiply", "screen", "overlay"] | None = Field(
        default=None, alias="blendMode"
    )

    model_config = {"populate_by_name": True}


class ConnectorEndpoint(BaseModel):
    target: dict[str, Any] | None = None
    anchor: str | dict[str, Any] | None = None
    offset: dict[str, float] | None = None
    element_id: str | None = Field(default=None, alias="elementId")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def normalize_legacy_endpoint(self) -> "ConnectorEndpoint":
        if self.target is None and self.element_id:
            self.target = {"type": "element", "elementId": self.element_id}
        return self

    @property
    def referenced_element_id(self) -> str | None:
        if self.target and self.target.get("type") == "element":
            value = self.target.get("elementId")
            return value if isinstance(value, str) else None
        return self.element_id


class CanvasSpec(BaseModel):
    width: PositiveFloat = 1280
    height: PositiveFloat = 720
    background: dict[str, str] = Field(
        default_factory=lambda: {"type": "solid", "color": "#ffffff"}
    )


class CanvasElement(BaseModel):
    """画布元素模型。

    新字段以 transform/layer/content/connector/asset 为主；旧字段保留为兼容层，
    让现有编排、引用解析和前端旧数据在迁移期仍然可以运行。
    """

    id: str
    type: ElementType
    name: str | None = None

    transform: ElementTransform
    layer: ElementLayer
    role: Literal["content", "decoration", "control", "annotation", "background"] | None = None
    interaction: dict[str, Any] | None = None
    semantic: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    content: dict[str, Any] | None = None
    box_style: dict[str, Any] | None = Field(default=None, alias="boxStyle")
    connector: dict[str, Any] | None = None
    image: dict[str, Any] | None = None
    asset: dict[str, Any] | None = None
    subject: dict[str, Any] | None = None
    children: list[str] | None = None
    group: dict[str, Any] | None = None

    x: float
    y: float
    width: PositiveFloat
    height: PositiveFloat
    z_index: int = Field(alias="zIndex")
    text: str | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    shape: str | dict[str, Any] | None = None
    label: str | None = None
    connector_type: str | None = Field(default=None, alias="connectorType")
    from_anchor: ConnectorEndpoint | None = Field(default=None, alias="from")
    to_anchor: ConnectorEndpoint | None = Field(default=None, alias="to")
    placeholder_style: dict[str, Any] | None = Field(default=None, alias="placeholderStyle")
    reason: str | None = None
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        migrated = dict(value)
        has_structured_transform = "transform" in migrated
        element_type = str(migrated.get("type") or "")

        transform = dict(migrated.get("transform") or {})
        for field_name in ("x", "y", "width", "height", "rotation", "opacity", "visible", "locked"):
            if field_name not in transform and field_name in migrated:
                transform[field_name] = migrated[field_name]
        migrated["transform"] = transform

        layer = dict(migrated.get("layer") or {})
        if "zIndex" not in layer and "zIndex" in migrated:
            layer["zIndex"] = migrated["zIndex"]
        if "zIndex" not in layer and "z_index" in migrated:
            layer["zIndex"] = migrated["z_index"]
        migrated["layer"] = layer

        for field_name in ("x", "y", "width", "height"):
            if field_name not in migrated and field_name in transform:
                migrated[field_name] = transform[field_name]
        if "zIndex" not in migrated and "zIndex" in layer:
            migrated["zIndex"] = layer["zIndex"]
        if "z_index" not in migrated and "zIndex" in layer:
            migrated["z_index"] = layer["zIndex"]

        content = dict(migrated.get("content") or {})
        if element_type == ElementType.TEXT and "text" not in content and migrated.get("text"):
            content["text"] = migrated["text"]
        if element_type == ElementType.SHAPE and "label" not in content and migrated.get("label"):
            content["label"] = migrated["label"]
        if element_type in {ElementType.IMAGE, ElementType.GENERATED_ASSET}:
            for field_name in ("assetId", "url", "alt"):
                if field_name not in content and field_name in migrated:
                    content[field_name] = migrated[field_name]
        if element_type == ElementType.CONNECTOR and "label" not in content and migrated.get("text"):
            content["label"] = migrated["text"]
        if content:
            migrated["content"] = content

        if element_type == ElementType.SHAPE and isinstance(migrated.get("shape"), str):
            migrated["shape"] = {"kind": migrated["shape"]}
        if element_type == ElementType.SHAPE and "shape" not in migrated and not has_structured_transform:
            migrated["shape"] = {"kind": "rectangle"}

        if element_type == ElementType.CONNECTOR:
            connector = dict(migrated.get("connector") or {})
            if "kind" not in connector:
                connector["kind"] = migrated.get("connectorType") or "line"
            if "from" not in connector and "from" in migrated:
                connector["from"] = cls._legacy_endpoint(migrated["from"])
            if "to" not in connector and "to" in migrated:
                connector["to"] = cls._legacy_endpoint(migrated["to"])
            connector.setdefault("routing", "straight")
            migrated["connector"] = connector

        return migrated

    @classmethod
    def _legacy_endpoint(cls, endpoint: Any) -> Any:
        if not isinstance(endpoint, dict):
            return endpoint
        if "target" in endpoint:
            return endpoint
        if "elementId" in endpoint:
            return {
                "target": {"type": "element", "elementId": endpoint["elementId"]},
                "anchor": endpoint.get("anchor"),
            }
        return endpoint

    @field_validator("x", "y")
    @classmethod
    def coordinate_must_be_finite(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("坐标必须是有限数字")
        return value

    @model_validator(mode="after")
    def validate_type_specific_payload(self) -> "CanvasElement":
        if self.type == ElementType.TEXT:
            if not isinstance(self.content, dict) or not self._non_empty_string(
                self.content.get("text")
            ):
                raise ValueError("text 元素必须提供 content.text")
            self.text = self.content["text"]

        if self.type == ElementType.SHAPE:
            if not isinstance(self.shape, dict) or not self._non_empty_string(self.shape.get("kind")):
                raise ValueError("shape 元素必须提供 shape.kind")
            if isinstance(self.content, dict) and self.content.get("label"):
                self.label = str(self.content["label"])

        if self.type == ElementType.CONNECTOR:
            if not isinstance(self.connector, dict):
                raise ValueError("connector 元素必须提供 connector")
            if "from" not in self.connector or "to" not in self.connector:
                raise ValueError("connector 元素必须提供 connector.from 和 connector.to")
            self.from_anchor = ConnectorEndpoint.model_validate(self.connector["from"])
            self.to_anchor = ConnectorEndpoint.model_validate(self.connector["to"])
            self.connector_type = str(self.connector.get("kind") or "line")
            if isinstance(self.content, dict) and self.content.get("label"):
                self.text = str(self.content["label"])

        if self.type == ElementType.GENERATED_ASSET:
            if not isinstance(self.asset, dict):
                raise ValueError("generated_asset 元素必须提供 asset")
            status = self.asset.get("status")
            if status not in {"pending", "generating", "ready", "failed"}:
                raise ValueError("generated_asset.asset.status 非法")
            has_resource = bool(
                isinstance(self.content, dict)
                and (self.content.get("assetId") or self.content.get("url"))
            )
            if status == "ready" and not has_resource:
                raise ValueError("generated_asset ready 状态必须提供 assetId 或 url")
            if status != "ready" and not self.placeholder_style:
                raise ValueError("generated_asset 非 ready 状态必须提供 placeholderStyle")

        if self.type == ElementType.GROUP and not self.children:
            raise ValueError("group 元素必须提供 children")

        return self

    @staticmethod
    def _non_empty_string(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())


class Scene(BaseModel):
    id: str
    name: str
    order: int
    canvas: CanvasSpec = Field(default_factory=CanvasSpec)
    elements: list[CanvasElement] = Field(default_factory=list)
    description: str | None = None

    @model_validator(mode="after")
    def validate_element_references(self) -> "Scene":
        element_ids = {element.id for element in self.elements}
        for element in self.elements:
            if element.type == ElementType.CONNECTOR:
                for endpoint in (element.from_anchor, element.to_anchor):
                    referenced_id = endpoint.referenced_element_id if endpoint else None
                    if referenced_id and referenced_id not in element_ids:
                        raise ValueError(f"connector 引用不存在的元素：{referenced_id}")

            if element.type == ElementType.GROUP:
                for child_id in element.children or []:
                    if child_id not in element_ids:
                        raise ValueError(f"group 引用不存在的元素：{child_id}")
                    if child_id == element.id:
                        raise ValueError("group 不能引用自身")
                if self._group_has_cycle(element.id, element_ids):
                    raise ValueError("group.children 不能形成循环引用")

        return self

    def _group_has_cycle(self, root_id: str, element_ids: set[str]) -> bool:
        group_children = {
            element.id: element.children or []
            for element in self.elements
            if element.type == ElementType.GROUP and element.id in element_ids
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(element_id: str) -> bool:
            if element_id in visiting:
                return True
            if element_id in visited:
                return False
            visiting.add(element_id)
            for child_id in group_children.get(element_id, []):
                if visit(child_id):
                    return True
            visiting.remove(element_id)
            visited.add(element_id)
            return False

        return visit(root_id)


class Project(BaseModel):
    id: str
    title: str
    mode: Literal["free_canvas", "storyboard"]
    scenes: list[Scene] = Field(min_length=1)
    active_scene_id: str = Field(alias="activeSceneId")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_scene_references(self) -> "Project":
        scene_ids = {scene.id for scene in self.scenes}
        if self.active_scene_id not in scene_ids:
            raise ValueError("activeSceneId 必须指向现有 Scene")

        orders = [scene.order for scene in self.scenes]
        if len(set(orders)) != len(orders):
            raise ValueError("Scene order 不能重复")

        return self
