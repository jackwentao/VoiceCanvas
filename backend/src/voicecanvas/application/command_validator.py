from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, ValidationError

from voicecanvas.application.element_patch import merge_element_patch
from voicecanvas.domain.commands import CanvasCommand, CommandType
from voicecanvas.domain.project import CanvasElement, CanvasSpec, Project, Scene

T = TypeVar("T")


class ValidationIssue(BaseModel):
    path: str
    code: str
    message: str
    severity: str = "error"


class ValidationResult(BaseModel, Generic[T]):
    ok: bool
    value: T | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)


class CommandValidator:
    """校验 AI 或工具生成的画布命令，确保执行器只处理可信输入。"""

    def validate(
        self, commands: list[CanvasCommand], project: Project
    ) -> ValidationResult[list[CanvasCommand]]:
        issues: list[ValidationIssue] = []

        for index, command in enumerate(commands):
            issues.extend(self._validate_command(command, project, f"commands.{index}"))

        if issues:
            return ValidationResult(ok=False, issues=issues)

        return ValidationResult(ok=True, value=commands)

    def _validate_command(
        self, command: CanvasCommand, project: Project, path: str
    ) -> list[ValidationIssue]:
        match command.type:
            case CommandType.UPDATE_PROJECT:
                return self._validate_update_project(command, path)
            case CommandType.CREATE_SCENE:
                return self._validate_create_scene(command, project, path)
            case CommandType.UPDATE_SCENE:
                return self._validate_update_scene(command, project, path)
            case CommandType.CLEAR_SCENE:
                return self._validate_clear_scene(command, project, path)
            case CommandType.DELETE_SCENE:
                return self._validate_delete_scene(command, project, path)
            case CommandType.SWITCH_SCENE:
                return self._validate_switch_scene(command, project, path)
            case CommandType.ADD_ELEMENT:
                return self._validate_add_element(command, project, path)
            case CommandType.UPDATE_ELEMENT:
                return self._validate_update_element(command, project, path)
            case CommandType.DELETE_ELEMENT:
                return self._validate_delete_element(command, project, path)
            case CommandType.ARRANGE_LAYOUT:
                return self._validate_arrange_layout(command, project, path)
            case CommandType.EXPORT_PROJECT:
                return self._validate_export_project(command, project, path)

    def _validate_update_project(
        self, command: CanvasCommand, path: str
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        patch = command.payload.get("patch")
        if not isinstance(patch, dict):
            return [
                self._issue(
                    f"{path}.payload.patch",
                    "missing_field",
                    "UPDATE_PROJECT 需要 patch",
                )
            ]

        allowed_fields = {"title"}
        for field_name in patch:
            if field_name not in allowed_fields:
                issues.append(
                    self._issue(
                        f"{path}.payload.patch.{field_name}",
                        "unsupported_field",
                        f"UPDATE_PROJECT 不支持更新 {field_name}",
                    )
                )

        if "title" in patch and not self._is_non_empty_string(patch["title"]):
            issues.append(
                self._issue(
                    f"{path}.payload.patch.title",
                    "invalid_field",
                    "项目名称不能为空",
                )
            )

        return issues

    def _validate_create_scene(
        self, command: CanvasCommand, project: Project, path: str
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        payload = command.payload
        if "scene" in payload:
            self._try_model(Scene, payload["scene"], f"{path}.payload.scene", issues)
            scene_name = (
                payload["scene"].get("name") if isinstance(payload["scene"], dict) else None
            )
            self._append_duplicate_scene_name_issue(
                issues,
                project,
                scene_name,
                f"{path}.payload.scene.name",
            )
            return issues

        scene_name = payload.get("name")
        if not self._is_non_empty_string(scene_name):
            issues.append(
                self._issue(f"{path}.payload.name", "missing_field", "CREATE_SCENE 需要 name")
            )
        else:
            self._append_duplicate_scene_name_issue(
                issues,
                project,
                scene_name,
                f"{path}.payload.name",
            )

        canvas = payload.get("canvas")
        if canvas is not None:
            self._try_model(CanvasSpec, canvas, f"{path}.payload.canvas", issues)

        return issues

    def _validate_update_scene(
        self, command: CanvasCommand, project: Project, path: str
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        payload = command.payload
        scene = self._find_scene(project, payload.get("sceneId"))
        if scene is None:
            issues.append(self._issue(f"{path}.payload.sceneId", "not_found", "目标 Scene 不存在"))

        patch = payload.get("patch")
        if not isinstance(patch, dict):
            issues.append(
                self._issue(
                    f"{path}.payload.patch",
                    "missing_field",
                    "UPDATE_SCENE 需要 patch",
                )
            )
            return issues

        allowed_fields = {"name", "description", "narration", "canvas"}
        if command.source == "system":
            allowed_fields.add("elements")

        for field_name in patch:
            if field_name not in allowed_fields:
                issues.append(
                    self._issue(
                        f"{path}.payload.patch.{field_name}",
                        "unsupported_field",
                        f"UPDATE_SCENE 不支持更新 {field_name}",
                    )
                )

        if "canvas" in patch:
            self._try_model(CanvasSpec, patch["canvas"], f"{path}.payload.patch.canvas", issues)
        if "name" in patch and scene is not None:
            self._append_duplicate_scene_name_issue(
                issues,
                project,
                patch["name"],
                f"{path}.payload.patch.name",
                ignored_scene_id=scene.id,
            )
        if "elements" in patch and command.source == "system":
            if not isinstance(patch["elements"], list):
                issues.append(
                    self._issue(
                        f"{path}.payload.patch.elements",
                        "invalid_field",
                        "elements 必须是数组",
                    )
                )
            else:
                for index, element in enumerate(patch["elements"]):
                    self._try_model(
                        CanvasElement,
                        element,
                        f"{path}.payload.patch.elements.{index}",
                        issues,
                    )

        return issues

    def _validate_clear_scene(
        self, command: CanvasCommand, project: Project, path: str
    ) -> list[ValidationIssue]:
        scene_id = command.payload.get("sceneId")
        if self._find_scene(project, scene_id) is None:
            return [self._issue(f"{path}.payload.sceneId", "not_found", "目标 Scene 不存在")]
        return []

    def _validate_delete_scene(
        self, command: CanvasCommand, project: Project, path: str
    ) -> list[ValidationIssue]:
        scene_id = command.payload.get("sceneId")
        if self._find_scene(project, scene_id) is None:
            return [self._issue(f"{path}.payload.sceneId", "not_found", "目标 Scene 不存在")]
        return []

    def _validate_switch_scene(
        self, command: CanvasCommand, project: Project, path: str
    ) -> list[ValidationIssue]:
        scene_id = command.payload.get("sceneId")
        if self._find_scene(project, scene_id) is None:
            return [self._issue(f"{path}.payload.sceneId", "not_found", "目标 Scene 不存在")]
        return []

    def _validate_add_element(
        self, command: CanvasCommand, project: Project, path: str
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        payload = command.payload
        scene = self._find_scene(project, payload.get("sceneId"))
        if scene is None:
            issues.append(self._issue(f"{path}.payload.sceneId", "not_found", "目标 Scene 不存在"))

        element = payload.get("element")
        if not isinstance(element, dict):
            issues.append(
                self._issue(
                    f"{path}.payload.element",
                    "missing_field",
                    "ADD_ELEMENT 需要 element",
                )
            )
            return issues

        draft = {"id": "el_validation_placeholder", **element}
        self._try_model(CanvasElement, draft, f"{path}.payload.element", issues)
        if scene is not None:
            self._try_model(
                Scene,
                {
                    **scene.model_dump(by_alias=True),
                    "elements": [
                        *[item.model_dump(by_alias=True) for item in scene.elements],
                        draft,
                    ],
                },
                f"{path}.payload.element",
                issues,
            )
        return issues

    def _validate_update_element(
        self, command: CanvasCommand, project: Project, path: str
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        payload = command.payload
        scene = self._find_scene(project, payload.get("sceneId"))
        if scene is None:
            issues.append(self._issue(f"{path}.payload.sceneId", "not_found", "目标 Scene 不存在"))
            return issues

        element = self._find_element(scene, payload.get("elementId"))
        if element is None:
            issues.append(
                self._issue(f"{path}.payload.elementId", "not_found", "目标 Element 不存在")
            )
            return issues

        patch = payload.get("patch")
        if not isinstance(patch, dict):
            issues.append(
                self._issue(
                    f"{path}.payload.patch",
                    "missing_field",
                    "UPDATE_ELEMENT 需要 patch",
                )
            )
            return issues

        allowed_fields = {
            "x",
            "y",
            "width",
            "height",
            "zIndex",
            "name",
            "description",
            "text",
            "style",
            "transform",
            "layer",
            "content",
            "boxStyle",
            "shape",
            "label",
            "connector",
            "connectorType",
            "from",
            "to",
            "image",
            "asset",
            "subject",
            "children",
            "group",
            "placeholderStyle",
            "reason",
            "role",
            "interaction",
            "semantic",
            "metadata",
        }
        for field_name in patch:
            if field_name not in allowed_fields:
                issues.append(
                    self._issue(
                        f"{path}.payload.patch.{field_name}",
                        "unsupported_field",
                        f"UPDATE_ELEMENT 不支持更新 {field_name}",
                    )
                )

        merged = merge_element_patch(element.model_dump(by_alias=True), patch)
        self._try_model(CanvasElement, merged, f"{path}.payload.patch", issues)
        self._try_model(
            Scene,
            {
                **scene.model_dump(by_alias=True),
                "elements": [
                    merged if item.id == element.id else item.model_dump(by_alias=True)
                    for item in scene.elements
                ],
            },
            f"{path}.payload.patch",
            issues,
        )
        return issues

    def _validate_delete_element(
        self, command: CanvasCommand, project: Project, path: str
    ) -> list[ValidationIssue]:
        payload = command.payload
        scene = self._find_scene(project, payload.get("sceneId"))
        if scene is None:
            return [self._issue(f"{path}.payload.sceneId", "not_found", "目标 Scene 不存在")]

        if self._find_element(scene, payload.get("elementId")) is None:
            return [self._issue(f"{path}.payload.elementId", "not_found", "目标 Element 不存在")]

        return []

    def _validate_arrange_layout(
        self, command: CanvasCommand, project: Project, path: str
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        payload = command.payload
        scene = self._find_scene(project, payload.get("sceneId"))
        if scene is None:
            issues.append(self._issue(f"{path}.payload.sceneId", "not_found", "目标 Scene 不存在"))
            return issues

        allowed_strategies = {"center", "bring_to_front", "send_to_back"}
        if command.source == "system":
            allowed_strategies.add("restore")

        if payload.get("strategy") not in allowed_strategies:
            issues.append(
                self._issue(
                    f"{path}.payload.strategy",
                    "unsupported_strategy",
                    "本阶段 ARRANGE_LAYOUT 只支持 center、bring_to_front、send_to_back",
                )
            )

        element_ids = payload.get("elementIds")
        if element_ids is not None:
            if not isinstance(element_ids, list) or not all(
                isinstance(element_id, str) for element_id in element_ids
            ):
                issues.append(
                    self._issue(
                        f"{path}.payload.elementIds",
                        "invalid_field",
                        "elementIds 必须是字符串数组",
                    )
                )
                return issues

            scene_element_ids = {element.id for element in scene.elements}
            for element_id in element_ids:
                if element_id not in scene_element_ids:
                    issues.append(
                        self._issue(
                            f"{path}.payload.elementIds",
                            "not_found",
                            f"目标 Element 不存在：{element_id}",
                        )
                    )

        return issues

    def _validate_export_project(
        self, command: CanvasCommand, project: Project, path: str
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        payload = command.payload
        export_format = payload.get("format", "json")
        scope = payload.get("scope", "project")

        if export_format not in {"json", "png"}:
            issues.append(
                self._issue(
                    f"{path}.payload.format",
                    "unsupported_format",
                    "EXPORT_PROJECT 仅支持 json、png",
                )
            )

        if scope not in {"project", "active_scene", "scene"}:
            issues.append(
                self._issue(
                    f"{path}.payload.scope",
                    "unsupported_scope",
                    "EXPORT_PROJECT 仅支持 project、active_scene、scene",
                )
            )

        if scope == "scene" and self._find_scene(project, payload.get("sceneId")) is None:
            issues.append(
                self._issue(
                    f"{path}.payload.sceneId",
                    "not_found",
                    "导出目标 Scene 不存在",
                )
            )

        return issues

    def _try_model(
        self,
        model_type: type[BaseModel],
        value: Any,
        path: str,
        issues: list[ValidationIssue],
    ) -> None:
        try:
            model_type.model_validate(value)
        except ValidationError as error:
            for item in error.errors():
                location = ".".join(str(part) for part in item["loc"])
                issues.append(
                    self._issue(
                        f"{path}.{location}" if location else path,
                        "invalid_field",
                        str(item["msg"]),
                    )
                )

    def _find_scene(self, project: Project, scene_id: Any) -> Scene | None:
        if not isinstance(scene_id, str):
            return None
        return next((scene for scene in project.scenes if scene.id == scene_id), None)

    def _find_element(self, scene: Scene, element_id: Any) -> CanvasElement | None:
        if not isinstance(element_id, str):
            return None
        return next((element for element in scene.elements if element.id == element_id), None)

    def _append_duplicate_scene_name_issue(
        self,
        issues: list[ValidationIssue],
        project: Project,
        scene_name: Any,
        path: str,
        *,
        ignored_scene_id: str | None = None,
    ) -> None:
        if not self._is_non_empty_string(scene_name):
            return

        normalized_name = str(scene_name).strip()
        has_duplicate = any(
            scene.id != ignored_scene_id and scene.name.strip() == normalized_name
            for scene in project.scenes
        )
        if has_duplicate:
            issues.append(
                self._issue(path, "duplicate_scene_name", "同一项目内 Scene name 不能重复")
            )

    def _is_non_empty_string(self, value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def _issue(self, path: str, code: str, message: str) -> ValidationIssue:
        return ValidationIssue(path=path, code=code, message=message)
