from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel

from voicecanvas.application.command_validator import CommandValidator
from voicecanvas.domain.commands import CanvasCommand, CommandType
from voicecanvas.domain.history import HistoryEntry
from voicecanvas.domain.patches import CanvasPatch, PatchType
from voicecanvas.domain.project import CanvasElement, Project, Scene


class CommandExecutionFailure(BaseModel):
    command: CanvasCommand
    error: str


class CommandExecutionResult(BaseModel):
    command_id: str
    project: Project
    patches: list[CanvasPatch]
    history_entry: HistoryEntry


class BatchExecutionResult(BaseModel):
    project: Project
    applied: list[CommandExecutionResult]
    failed: CommandExecutionFailure | None = None


class CommandExecutor:
    """确定性执行画布命令，统一产出 Project、Patch 和 History。"""

    def __init__(self, validator: CommandValidator | None = None) -> None:
        self._validator = validator or CommandValidator()

    def execute(self, command: CanvasCommand, project: Project) -> CommandExecutionResult:
        validation = self._validator.validate([command], project)
        if not validation.ok:
            messages = "；".join(issue.message for issue in validation.issues)
            raise ValueError(messages)
        return self.apply_without_recording(command, project)

    def execute_batch(
        self, commands: list[CanvasCommand], project: Project
    ) -> BatchExecutionResult:
        current_project = project
        applied: list[CommandExecutionResult] = []

        for command in commands:
            validation = self._validator.validate([command], current_project)
            if not validation.ok:
                messages = "；".join(issue.message for issue in validation.issues)
                return BatchExecutionResult(
                    project=current_project,
                    applied=applied,
                    failed=CommandExecutionFailure(command=command, error=messages),
                )

            try:
                result = self.apply_without_recording(command, current_project)
            except ValueError as error:
                return BatchExecutionResult(
                    project=current_project,
                    applied=applied,
                    failed=CommandExecutionFailure(command=command, error=str(error)),
                )

            applied.append(result)
            current_project = result.project

        return BatchExecutionResult(project=current_project, applied=applied)

    def apply_without_recording(
        self, command: CanvasCommand, project: Project
    ) -> CommandExecutionResult:
        match command.type:
            case CommandType.CREATE_SCENE:
                return self._create_scene(command, project)
            case CommandType.UPDATE_SCENE:
                return self._update_scene(command, project)
            case CommandType.DELETE_SCENE:
                return self._delete_scene(command, project)
            case CommandType.SWITCH_SCENE:
                return self._switch_scene(command, project)
            case CommandType.ADD_ELEMENT:
                return self._add_element(command, project)
            case CommandType.UPDATE_ELEMENT:
                return self._update_element(command, project)
            case CommandType.DELETE_ELEMENT:
                return self._delete_element(command, project)
            case CommandType.ARRANGE_LAYOUT:
                return self._arrange_layout(command, project)
            case CommandType.EXPORT_PROJECT:
                raise ValueError("EXPORT_PROJECT 将由后续 Exporter 模块执行")

    def _create_scene(self, command: CanvasCommand, project: Project) -> CommandExecutionResult:
        payload = command.payload
        scene = (
            Scene.model_validate(payload["scene"])
            if "scene" in payload
            else Scene(
                id=f"scene_{uuid4().hex[:12]}",
                name=payload["name"],
                description=payload.get("description"),
                order=max(scene.order for scene in project.scenes) + 1,
                canvas=payload.get("canvas", {}),
            )
        )
        activate = bool(payload.get("activate", True))
        active_scene_id = scene.id if activate else project.active_scene_id
        next_project = project.model_copy(
            update={
                "scenes": [*project.scenes, scene],
                "active_scene_id": active_scene_id,
            }
        )
        patches = [
            self._patch(command.id, PatchType.SCENE_CREATED, scene_id=scene.id, scene=scene)
        ]
        if activate and project.active_scene_id != scene.id:
            patches.append(
                self._patch(
                    command.id,
                    PatchType.ACTIVE_SCENE_CHANGED,
                    scene_id=scene.id,
                    patch={"previousSceneId": project.active_scene_id},
                )
            )

        applied_command = command.model_copy(
            update={"payload": {**payload, "scene": scene.model_dump(by_alias=True)}}
        )
        inverse = self._command(
            command.id,
            CommandType.DELETE_SCENE,
            {"sceneId": scene.id},
            reason="撤销创建镜头",
        )
        return self._result(
            applied_command,
            next_project,
            patches,
            inverse,
            f"创建镜头：{scene.name}",
        )

    def _update_scene(self, command: CanvasCommand, project: Project) -> CommandExecutionResult:
        scene_id = command.payload["sceneId"]
        patch = command.payload["patch"]
        scene = self._require_scene(project, scene_id)
        before = scene.model_dump(by_alias=True)
        merged = {**before, **patch}
        updated_scene = Scene.model_validate(merged)
        scenes = [updated_scene if item.id == scene_id else item for item in project.scenes]
        next_project = project.model_copy(update={"scenes": scenes})
        actual_patch = {
            key: value for key, value in patch.items() if before.get(key) != value
        }
        inverse_patch = {key: before.get(key) for key in actual_patch}
        inverse = self._command(
            command.id,
            CommandType.UPDATE_SCENE,
            {"sceneId": scene_id, "patch": inverse_patch},
            source="system",
            reason="撤销修改镜头",
        )
        patches = [
            self._patch(
                command.id,
                PatchType.SCENE_UPDATED,
                scene_id=scene_id,
                patch=actual_patch,
            )
        ]
        return self._result(command, next_project, patches, inverse, f"修改镜头：{scene.name}")

    def _delete_scene(self, command: CanvasCommand, project: Project) -> CommandExecutionResult:
        scene_id = command.payload["sceneId"]
        scene = self._require_scene(project, scene_id)

        if len(project.scenes) == 1:
            cleared_scene = scene.model_copy(update={"elements": [], "description": None})
            next_project = project.model_copy(update={"scenes": [cleared_scene]})
            patches = [
                self._patch(
                    command.id,
                    PatchType.SCENE_CLEARED,
                    scene_id=scene_id,
                    patch={"clearedElementIds": [element.id for element in scene.elements]},
                )
            ]
            inverse = self._command(
                command.id,
                CommandType.UPDATE_SCENE,
                {
                    "sceneId": scene_id,
                    "patch": {
                        "description": scene.description,
                        "elements": [
                            element.model_dump(by_alias=True) for element in scene.elements
                        ],
                    },
                },
                source="system",
                reason="撤销清空页面",
            )
            return self._result(
                command,
                next_project,
                patches,
                inverse,
                f"清空页面：{scene.name}",
            )

        remaining_scenes = [item for item in project.scenes if item.id != scene_id]
        active_scene_id = project.active_scene_id
        patches = [
            self._patch(command.id, PatchType.SCENE_DELETED, scene_id=scene_id, scene=scene)
        ]

        if project.active_scene_id == scene_id:
            active_scene_id = self._choose_next_active_scene(project.scenes, scene).id
            patches.append(
                self._patch(
                    command.id,
                    PatchType.ACTIVE_SCENE_CHANGED,
                    scene_id=active_scene_id,
                    patch={"previousSceneId": scene_id},
                )
            )

        next_project = project.model_copy(
            update={"scenes": remaining_scenes, "active_scene_id": active_scene_id}
        )
        inverse = self._command(
            command.id,
            CommandType.CREATE_SCENE,
            {
                "scene": scene.model_dump(by_alias=True),
                "activate": project.active_scene_id == scene_id,
            },
            reason="撤销删除镜头",
        )
        return self._result(command, next_project, patches, inverse, f"删除镜头：{scene.name}")

    def _switch_scene(self, command: CanvasCommand, project: Project) -> CommandExecutionResult:
        scene_id = command.payload["sceneId"]
        scene = self._require_scene(project, scene_id)
        next_project = project.model_copy(update={"active_scene_id": scene_id})
        patches = [
            self._patch(
                command.id,
                PatchType.ACTIVE_SCENE_CHANGED,
                scene_id=scene_id,
                patch={"previousSceneId": project.active_scene_id},
            )
        ]
        inverse = self._command(
            command.id,
            CommandType.SWITCH_SCENE,
            {"sceneId": project.active_scene_id},
            reason="撤销切换镜头",
        )
        return self._result(command, next_project, patches, inverse, f"切换镜头：{scene.name}")

    def _add_element(self, command: CanvasCommand, project: Project) -> CommandExecutionResult:
        scene_id = command.payload["sceneId"]
        scene = self._require_scene(project, scene_id)
        element_payload = dict(command.payload["element"])
        element_payload.setdefault("id", f"el_{uuid4().hex[:12]}")
        element = CanvasElement.model_validate(element_payload)
        updated_scene = scene.model_copy(update={"elements": [*scene.elements, element]})
        next_project = self._replace_scene(project, updated_scene)
        patches = [
            self._patch(
                command.id,
                PatchType.ELEMENT_ADDED,
                scene_id=scene_id,
                element_id=element.id,
                element=element,
            )
        ]
        applied_command = command.model_copy(
            update={
                "payload": {
                    **command.payload,
                    "element": element.model_dump(by_alias=True),
                }
            }
        )
        inverse = self._command(
            command.id,
            CommandType.DELETE_ELEMENT,
            {"sceneId": scene_id, "elementId": element.id},
            reason="撤销新增元素",
        )
        return self._result(
            applied_command,
            next_project,
            patches,
            inverse,
            f"新增元素：{element.name or element.id}",
        )

    def _update_element(self, command: CanvasCommand, project: Project) -> CommandExecutionResult:
        scene_id = command.payload["sceneId"]
        element_id = command.payload["elementId"]
        patch = command.payload["patch"]
        scene = self._require_scene(project, scene_id)
        element = self._require_element(scene, element_id)
        before = element.model_dump(by_alias=True)
        merged = self._merge_element_patch(before, patch)
        updated_element = CanvasElement.model_validate(merged)
        updated_scene = scene.model_copy(
            update={
                "elements": [
                    updated_element if item.id == element_id else item for item in scene.elements
                ]
            }
        )
        next_project = self._replace_scene(project, updated_scene)
        actual_patch = {key: value for key, value in patch.items() if before.get(key) != value}
        inverse_patch = {key: before.get(key) for key in actual_patch}
        inverse = self._command(
            command.id,
            CommandType.UPDATE_ELEMENT,
            {"sceneId": scene_id, "elementId": element_id, "patch": inverse_patch},
            reason="撤销修改元素",
        )
        patches = [
            self._patch(
                command.id,
                PatchType.ELEMENT_UPDATED,
                scene_id=scene_id,
                element_id=element_id,
                patch=actual_patch,
            )
        ]
        return self._result(
            command,
            next_project,
            patches,
            inverse,
            f"修改元素：{element.name or element.id}",
        )

    def _delete_element(self, command: CanvasCommand, project: Project) -> CommandExecutionResult:
        scene_id = command.payload["sceneId"]
        element_id = command.payload["elementId"]
        scene = self._require_scene(project, scene_id)
        element = self._require_element(scene, element_id)
        original_elements = [item.model_dump(by_alias=True) for item in scene.elements]
        updated_scene = scene.model_copy(
            update={
                "elements": [
                    self._degrade_connector(command.id, item, element_id)
                    for item in scene.elements
                    if item.id != element_id
                ]
            }
        )
        next_project = self._replace_scene(project, updated_scene)
        patches = [
            self._patch(
                command.id,
                PatchType.ELEMENT_DELETED,
                scene_id=scene_id,
                element_id=element_id,
                element=element,
            )
        ]
        for item in scene.elements:
            if item.id != element_id and self._connector_references(item, element_id):
                patches.append(
                    self._patch(
                        command.id,
                        PatchType.ELEMENT_UPDATED,
                        scene_id=scene_id,
                        element_id=item.id,
                        patch={
                            "type": "unknown",
                            "reason": "invalid_reference",
                            "label": "连接线目标已删除",
                            "metadata": {
                                **(item.metadata or {}),
                                "invalidConnectorOfDeletedElement": element_id,
                            },
                        },
                    )
                )
        inverse = self._command(
            command.id,
            CommandType.UPDATE_SCENE,
            {"sceneId": scene_id, "patch": {"elements": original_elements}},
            source="system",
            reason="撤销删除元素并恢复连接线引用",
        )
        return self._result(
            command,
            next_project,
            patches,
            inverse,
            f"删除元素：{element.name or element.id}",
        )

    def _arrange_layout(self, command: CanvasCommand, project: Project) -> CommandExecutionResult:
        scene_id = command.payload["sceneId"]
        strategy = command.payload["strategy"]
        scene = self._require_scene(project, scene_id)
        target_ids = command.payload.get("elementIds") or [element.id for element in scene.elements]
        target_id_set = set(target_ids)
        if strategy == "restore":
            return self._restore_layout(command, project, scene, target_id_set)

        max_z_index = max((element.z_index for element in scene.elements), default=0)
        min_z_index = min((element.z_index for element in scene.elements), default=0)
        updated_elements: list[CanvasElement] = []
        inverse_patches: dict[str, dict[str, Any]] = {}
        patches: list[CanvasPatch] = []

        for element in scene.elements:
            if element.id not in target_id_set:
                updated_elements.append(element)
                continue

            element_patch: dict[str, Any] = {}
            if strategy == "center":
                element_patch = {
                    "x": (scene.canvas.width - element.width) / 2,
                    "y": (scene.canvas.height - element.height) / 2,
                }
            elif strategy == "bring_to_front":
                element_patch = {"zIndex": max_z_index + 1}
                max_z_index += 1
            elif strategy == "send_to_back":
                element_patch = {"zIndex": min_z_index - 1}
                min_z_index -= 1

            before = element.model_dump(by_alias=True)
            inverse_patches[element.id] = self._changed_previous_values(before, element_patch)
            updated_element = CanvasElement.model_validate({**before, **element_patch})
            updated_elements.append(updated_element)
            patches.append(
                self._patch(
                    command.id,
                    PatchType.ELEMENT_UPDATED,
                    scene_id=scene_id,
                    element_id=element.id,
                    patch=element_patch,
                )
            )

        updated_scene = scene.model_copy(update={"elements": updated_elements})
        next_project = self._replace_scene(project, updated_scene)
        inverse = self._command(
            command.id,
            CommandType.ARRANGE_LAYOUT,
            {
                "sceneId": scene_id,
                "strategy": "restore",
                "elementIds": target_ids,
                "patches": inverse_patches,
            },
            source="system",
            reason="撤销布局调整",
        )

        return self._result(command, next_project, patches, inverse, "调整布局")

    def _restore_layout(
        self,
        command: CanvasCommand,
        project: Project,
        scene: Scene,
        target_id_set: set[str],
    ) -> CommandExecutionResult:
        inverse_source_patches = command.payload.get("patches", {})
        if not isinstance(inverse_source_patches, dict):
            raise ValueError("restore 需要 patches")

        updated_elements: list[CanvasElement] = []
        redo_patches: dict[str, dict[str, Any]] = {}
        patches: list[CanvasPatch] = []

        for element in scene.elements:
            if element.id not in target_id_set:
                updated_elements.append(element)
                continue

            element_patch = inverse_source_patches.get(element.id, {})
            if not isinstance(element_patch, dict):
                raise ValueError(f"restore patch 非法：{element.id}")

            before = element.model_dump(by_alias=True)
            redo_patches[element.id] = self._changed_previous_values(before, element_patch)
            updated_element = CanvasElement.model_validate({**before, **element_patch})
            updated_elements.append(updated_element)
            patches.append(
                self._patch(
                    command.id,
                    PatchType.ELEMENT_UPDATED,
                    scene_id=scene.id,
                    element_id=element.id,
                    patch=element_patch,
                )
            )

        updated_scene = scene.model_copy(update={"elements": updated_elements})
        next_project = self._replace_scene(project, updated_scene)
        inverse = self._command(
            command.id,
            CommandType.ARRANGE_LAYOUT,
            {
                "sceneId": scene.id,
                "strategy": "restore",
                "elementIds": list(target_id_set),
                "patches": redo_patches,
            },
            source="system",
            reason="重做布局调整",
        )
        return self._result(command, next_project, patches, inverse, "恢复布局")

    def _result(
        self,
        command: CanvasCommand,
        project: Project,
        patches: list[CanvasPatch],
        inverse_command: CanvasCommand,
        summary: str,
    ) -> CommandExecutionResult:
        history_entry = HistoryEntry(
            id=f"history_{uuid4().hex[:12]}",
            command=command,
            patches=patches,
            inverseCommand=inverse_command,
            summary=summary,
            createdAt=self._now(),
        )
        return CommandExecutionResult(
            command_id=command.id,
            project=project,
            patches=patches,
            history_entry=history_entry,
        )

    def _command(
        self,
        seed_command_id: str,
        command_type: CommandType,
        payload: dict[str, Any],
        *,
        source: Literal["ai", "tool", "user_ui", "system"] = "system",
        reason: str,
    ) -> CanvasCommand:
        return CanvasCommand(
            id=f"{seed_command_id}_inverse",
            type=command_type,
            source=source,
            payload=payload,
            reason=reason,
            createdAt=self._now(),
        )

    def _patch(
        self,
        command_id: str,
        patch_type: PatchType,
        *,
        scene_id: str | None = None,
        element_id: str | None = None,
        scene: Scene | None = None,
        element: CanvasElement | None = None,
        patch: dict[str, Any] | None = None,
    ) -> CanvasPatch:
        return CanvasPatch(
            id=f"patch_{uuid4().hex[:12]}",
            type=patch_type,
            commandId=command_id,
            createdAt=self._now(),
            sceneId=scene_id,
            elementId=element_id,
            scene=scene,
            element=element,
            patch=patch or {},
        )

    def _replace_scene(self, project: Project, updated_scene: Scene) -> Project:
        return project.model_copy(
            update={
                "scenes": [
                    updated_scene if scene.id == updated_scene.id else scene
                    for scene in project.scenes
                ]
            }
        )

    def _require_scene(self, project: Project, scene_id: str) -> Scene:
        scene = next((item for item in project.scenes if item.id == scene_id), None)
        if scene is None:
            raise ValueError(f"目标 Scene 不存在：{scene_id}")
        return scene

    def _require_element(self, scene: Scene, element_id: str) -> CanvasElement:
        element = next((item for item in scene.elements if item.id == element_id), None)
        if element is None:
            raise ValueError(f"目标 Element 不存在：{element_id}")
        return element

    def _choose_next_active_scene(self, scenes: list[Scene], deleted_scene: Scene) -> Scene:
        remaining = [scene for scene in scenes if scene.id != deleted_scene.id]
        before = [scene for scene in remaining if scene.order < deleted_scene.order]
        if before:
            return max(before, key=lambda scene: scene.order)
        return min(remaining, key=lambda scene: scene.order)

    def _changed_previous_values(
        self, before: dict[str, Any], patch: dict[str, Any]
    ) -> dict[str, Any]:
        return {key: before.get(key) for key in patch if before.get(key) != patch[key]}

    def _merge_element_patch(self, before: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = dict(before)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
            if key == "text":
                content = dict(merged.get("content") or {})
                content["text"] = value
                merged["content"] = content
            if key == "label":
                content = dict(merged.get("content") or {})
                content["label"] = value
                merged["content"] = content
        return merged

    def _connector_references(self, element: CanvasElement, target_element_id: str) -> bool:
        if element.type != "connector":
            return False
        endpoints = [element.from_anchor, element.to_anchor]
        return any(
            endpoint is not None and endpoint.referenced_element_id == target_element_id
            for endpoint in endpoints
        )

    def _degrade_connector(
        self, command_id: str, element: CanvasElement, deleted_element_id: str
    ) -> CanvasElement:
        if not self._connector_references(element, deleted_element_id):
            return element

        payload = {
            **element.model_dump(by_alias=True),
            "type": "unknown",
            "label": "连接线目标已删除",
            "reason": "invalid_reference",
            "placeholderStyle": {
                "fill": "#fff8ef",
                "stroke": "#f15b4a",
                "strokeWidth": 2,
                "radius": 8,
            },
            "metadata": {
                **(element.metadata or {}),
                "invalidatedByCommandId": command_id,
                "invalidConnectorOfDeletedElement": deleted_element_id,
            },
        }
        return CanvasElement.model_validate(payload)

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
