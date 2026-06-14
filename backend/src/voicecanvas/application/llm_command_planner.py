import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError, model_validator

from voicecanvas.adapters.llm.base import LLMClient, LLMClientError, LLMMessage
from voicecanvas.application.command_executor import CommandExecutor
from voicecanvas.application.command_planner import (
    CommandPlan,
    CommandPlanner,
    PlannerAttempt,
    PlanningContext,
)
from voicecanvas.application.command_validator import CommandValidator
from voicecanvas.application.referent_resolver import (
    ElementCandidate,
    ReferentResolver,
    resolution_to_next_action,
)
from voicecanvas.application.render_catalog import RenderCatalog, get_render_catalog
from voicecanvas.domain.commands import CanvasCommand, CommandType
from voicecanvas.domain.project import Project
from voicecanvas.domain.telemetry import TokenUsage


class LLMCommandDraft(BaseModel):
    """LLM 输出的命令草稿；系统会补齐 id/source/createdAt。"""

    type: CommandType
    payload: dict[str, Any]
    reason: str | None = None


class LLMCommandPlanOutput(BaseModel):
    """真实 LLM 必须返回的结构化规划结果。"""

    action: Literal["commands", "undo", "redo", "respond"]
    message: str = Field(min_length=1)
    commands: list[LLMCommandDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_action_commands(self) -> "LLMCommandPlanOutput":
        if self.action == "commands" and not self.commands:
            raise ValueError("action=commands 时 commands 不能为空")
        if self.action != "commands" and self.commands:
            raise ValueError("非 commands 动作不能携带 commands")
        return self


class LLMCommandPlanner:
    """使用真实 LLM 生成结构化画布命令，并在失败后重试与降级。"""

    def __init__(
        self,
        client: LLMClient,
        *,
        fallback_planner: CommandPlanner | None = None,
        validator: CommandValidator | None = None,
        referent_resolver: ReferentResolver | None = None,
        render_catalog: RenderCatalog | None = None,
        max_attempts: int = 3,
        temperature: float = 0.1,
        timeout_seconds: float = 20,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts 必须大于等于 1")
        self._client = client
        self._fallback_planner = fallback_planner
        self._validator = validator or CommandValidator()
        self._executor = CommandExecutor(self._validator)
        self._referent_resolver = referent_resolver or ReferentResolver()
        self._render_catalog = render_catalog or get_render_catalog()
        self._max_attempts = max_attempts
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds

    def plan(
        self,
        user_input: str,
        project: Project,
        *,
        context: PlanningContext | None = None,
    ) -> CommandPlan:
        attempts: list[PlannerAttempt] = []
        feedback: list[str] = []
        token_usage = TokenUsage()
        resolved_target = self._resolve_referent_before_llm(user_input, project, context)
        if isinstance(resolved_target, CommandPlan):
            return resolved_target

        for attempt_index in range(1, self._max_attempts + 1):
            raw_output: str | None = None
            try:
                completion = self._client.complete_json(
                    self._messages(user_input, project, feedback, resolved_target, context),
                    temperature=self._temperature,
                    timeout_seconds=self._timeout_seconds,
                )
                raw_output = completion.content
                token_usage = token_usage.plus(completion.usage)
                output = self._parse_output(raw_output)
                plan = self._to_command_plan(output, project, user_input, attempts)
                attempts.append(
                    PlannerAttempt(attempt=attempt_index, raw_output=raw_output, validated=True)
                )
                return CommandPlan(
                    action=plan.action,
                    commands=plan.commands,
                    message=plan.message,
                    attempts=attempts,
                    token_usage=token_usage,
                )
            except LLMClientError as error:
                attempts.append(
                    PlannerAttempt(
                        attempt=attempt_index,
                        error=f"{error.category}: {error.message}",
                    )
                )
                feedback.append(self._retry_feedback(error.category, error.message))
            except (ValidationError, ValueError) as error:
                attempts.append(
                    PlannerAttempt(
                        attempt=attempt_index,
                        raw_output=raw_output,
                        error=str(error),
                    )
                )
                feedback.append(f"上一次输出未通过校验：{error}")

        return self._fallback_or_response(user_input, project, attempts, token_usage)

    def _resolve_referent_before_llm(
        self,
        user_input: str,
        project: Project,
        context: PlanningContext | None = None,
    ) -> ElementCandidate | CommandPlan | None:
        memory = context.conversation if context is not None else None
        resolution = self._referent_resolver.resolve(user_input, project, memory)
        if resolution is None:
            return None
        if resolution.status == "matched":
            return resolution.candidates[0]

        return CommandPlan(
            "ask_clarification",
            [],
            resolution.question or "我需要先确认你想操作哪个画布元素。",
            next_action=resolution_to_next_action(resolution, session_id="pending"),
        )

    def _parse_output(self, raw_output: str) -> LLMCommandPlanOutput:
        json_text = self._extract_json(raw_output)
        return LLMCommandPlanOutput.model_validate_json(json_text)

    def _to_command_plan(
        self,
        output: LLMCommandPlanOutput,
        project: Project,
        user_input: str,
        attempts: list[PlannerAttempt],
    ) -> CommandPlan:
        if output.action != "commands":
            if output.action == "respond" and self._looks_actionable(user_input):
                raise ValueError(
                    "用户输入是明确的画布操作请求，不能只返回 respond；"
                    "请使用合理默认值生成 commands"
                )
            return CommandPlan(output.action, [], output.message, attempts=attempts)

        commands: list[CanvasCommand] = []
        element_aliases = self._element_aliases_from_project(project)
        for index, draft in enumerate(output.commands):
            for command_type, payload, reason in self._normalize_draft(
                draft,
                project,
                index,
                element_aliases,
            ):
                command = CanvasCommand(
                    id=f"cmd_{uuid4().hex[:12]}",
                    type=command_type,
                    source="ai",
                    payload=payload,
                    reason=reason,
                    createdAt=datetime.now(UTC).isoformat(),
                )
                commands.append(command)
                if command.type == CommandType.ADD_ELEMENT:
                    self._register_element_aliases(
                        element_aliases,
                        command.payload.get("element"),
                    )

        self._validate_commands_sequentially(commands, project)

        return CommandPlan("commands", commands, output.message, attempts=attempts)

    def _normalize_draft(
        self,
        draft: LLMCommandDraft,
        project: Project,
        index: int,
        element_aliases: dict[str, str],
    ) -> list[tuple[CommandType, dict[str, Any], str | None]]:
        payload = deepcopy(draft.payload)

        if draft.type == CommandType.ADD_ELEMENT:
            payload.setdefault("sceneId", project.active_scene_id)
            if isinstance(payload.get("element"), dict):
                payload["element"] = self._normalize_element(
                    payload["element"],
                    require_id=True,
                    element_aliases=element_aliases,
                )
            return [(draft.type, payload, draft.reason)]

        if draft.type == CommandType.CREATE_SCENE:
            if isinstance(payload.get("scene"), dict):
                next_order = max(scene.order for scene in project.scenes) + index + 1
                payload["scene"] = self._normalize_scene(
                    payload["scene"],
                    next_order,
                    element_aliases,
                )
            return [(draft.type, payload, draft.reason)]

        if draft.type == CommandType.UPDATE_SCENE:
            return self._normalize_update_scene(draft, payload, project, element_aliases)

        if draft.type == CommandType.UPDATE_ELEMENT:
            return [
                (
                    draft.type,
                    self._normalize_update_element_payload(payload, project),
                    draft.reason,
                )
            ]

        if draft.type == CommandType.EXPORT_PROJECT:
            payload.setdefault("format", "json")
            payload.setdefault(
                "scope",
                "project" if payload.get("format") in {"json", "project"} else "active_scene",
            )
            return [(draft.type, payload, draft.reason)]

        return [(draft.type, payload, draft.reason)]

    def _normalize_update_scene(
        self,
        draft: LLMCommandDraft,
        payload: dict[str, Any],
        project: Project,
        element_aliases: dict[str, str],
    ) -> list[tuple[CommandType, dict[str, Any], str | None]]:
        if "sceneId" in payload and isinstance(payload.get("patch"), dict):
            return self._normalize_scene_patch_with_elements(draft, payload, element_aliases)

        if "sceneId" in payload:
            scene_source = (
                payload.get("scene")
                if isinstance(payload.get("scene"), dict)
                else payload
            )
            return self._normalize_scene_like_update(
                draft,
                payload["sceneId"],
                scene_source,
                element_aliases,
            )

        scene = payload.get("scene")
        if not isinstance(scene, dict):
            return [(draft.type, payload, draft.reason)]

        commands: list[tuple[CommandType, dict[str, Any], str | None]] = []
        patch = {
            key: scene[key]
            for key in ("name", "description", "narration", "canvas")
            if key in scene
        }
        if patch:
            commands.append(
                (
                    CommandType.UPDATE_SCENE,
                    {"sceneId": project.active_scene_id, "patch": patch},
                    draft.reason,
                )
            )

        elements = scene.get("elements")
        if isinstance(elements, list):
            for element in elements:
                if isinstance(element, dict):
                    normalized_element = self._normalize_element(
                        element,
                        require_id=True,
                        element_aliases=element_aliases,
                    )
                    commands.append(
                        (
                            CommandType.ADD_ELEMENT,
                            {
                                "sceneId": project.active_scene_id,
                                "element": normalized_element,
                            },
                            "补充镜头元素",
                        )
                    )
                    self._register_element_aliases(element_aliases, normalized_element)

        return commands or [(draft.type, payload, draft.reason)]

    def _normalize_scene_like_update(
        self,
        draft: LLMCommandDraft,
        scene_id: str,
        scene_source: dict[str, Any],
        element_aliases: dict[str, str],
    ) -> list[tuple[CommandType, dict[str, Any], str | None]]:
        patch = {
            key: scene_source[key]
            for key in ("name", "description", "narration", "canvas")
            if key in scene_source
        }
        commands: list[tuple[CommandType, dict[str, Any], str | None]] = []
        if patch:
            commands.append(
                (
                    CommandType.UPDATE_SCENE,
                    {"sceneId": scene_id, "patch": patch},
                    draft.reason,
                )
            )

        elements = scene_source.get("elements")
        if isinstance(elements, list):
            for element in elements:
                if isinstance(element, dict):
                    normalized_element = self._normalize_element(
                        element,
                        require_id=True,
                        element_aliases=element_aliases,
                    )
                    commands.append(
                        (
                            CommandType.ADD_ELEMENT,
                            {
                                "sceneId": scene_id,
                                "element": normalized_element,
                            },
                            "补充镜头元素",
                        )
                    )
                    self._register_element_aliases(element_aliases, normalized_element)

        return commands or [(draft.type, {"sceneId": scene_id, "patch": {}}, draft.reason)]

    def _normalize_scene_patch_with_elements(
        self,
        draft: LLMCommandDraft,
        payload: dict[str, Any],
        element_aliases: dict[str, str],
    ) -> list[tuple[CommandType, dict[str, Any], str | None]]:
        scene_id = payload["sceneId"]
        source_patch = deepcopy(payload["patch"])
        elements = source_patch.pop("elements", None)
        patch = {
            key: source_patch[key]
            for key in ("name", "description", "narration", "canvas")
            if key in source_patch
        }

        commands: list[tuple[CommandType, dict[str, Any], str | None]] = []
        if patch:
            commands.append(
                (
                    CommandType.UPDATE_SCENE,
                    {"sceneId": scene_id, "patch": patch},
                    draft.reason,
                )
            )

        if isinstance(elements, list):
            for element in elements:
                if isinstance(element, dict):
                    normalized_element = self._normalize_element(
                        element,
                        require_id=True,
                        element_aliases=element_aliases,
                    )
                    commands.append(
                        (
                            CommandType.ADD_ELEMENT,
                            {
                                "sceneId": scene_id,
                                "element": normalized_element,
                            },
                            "补充镜头元素",
                        )
                    )
                    self._register_element_aliases(element_aliases, normalized_element)

        return commands or [(draft.type, payload, draft.reason)]

    def _normalize_update_element_payload(
        self,
        payload: dict[str, Any],
        project: Project,
    ) -> dict[str, Any]:
        if "elementId" not in payload and isinstance(payload.get("id"), str):
            payload["elementId"] = payload["id"]

        element_id = payload.get("elementId")
        if "sceneId" not in payload and isinstance(element_id, str):
            scene_id = self._find_scene_id_by_element(project, element_id)
            if scene_id is not None:
                payload["sceneId"] = scene_id

        if "patch" not in payload:
            patch: dict[str, Any] = {}
            updates = payload.get("updates")
            if isinstance(updates, dict):
                patch.update(updates)
            for key in ("text", "name", "x", "y", "width", "height", "zIndex", "style"):
                if key in payload:
                    patch[key] = payload[key]
            if patch:
                payload["patch"] = patch

        return payload

    def _normalize_scene(
        self,
        scene: dict[str, Any],
        order: int,
        element_aliases: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        normalized = deepcopy(scene)
        normalized.setdefault("id", f"scene_ai_{uuid4().hex[:12]}")
        normalized.setdefault("order", order)
        elements = normalized.get("elements")
        if isinstance(elements, list):
            scene_aliases = dict(element_aliases or {})
            normalized_elements = []
            for element in elements:
                if not isinstance(element, dict):
                    continue
                normalized_element = self._normalize_element(
                    element,
                    require_id=True,
                    element_aliases=scene_aliases,
                )
                normalized_elements.append(normalized_element)
                self._register_element_aliases(scene_aliases, normalized_element)
            normalized["elements"] = normalized_elements
        return normalized

    def _normalize_element(
        self,
        element: dict[str, Any],
        *,
        require_id: bool = False,
        element_aliases: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        normalized = deepcopy(element)
        properties = normalized.pop("properties", None)
        style = dict(normalized.get("style") or {})

        if require_id:
            normalized.setdefault("id", f"el_ai_{uuid4().hex[:12]}")
        if "textContent" in normalized and "text" not in normalized:
            normalized["text"] = normalized.pop("textContent")
        if isinstance(normalized.get("content"), str) and "text" not in normalized:
            normalized["text"] = normalized.pop("content")
        if isinstance(normalized.get("content"), dict) and "text" not in normalized:
            content_text = normalized["content"].get("text")
            if isinstance(content_text, str):
                normalized["text"] = content_text
        if "shapeType" in normalized and "shape" not in normalized:
            normalized["shape"] = normalized.pop("shapeType")
        if "backgroundColor" in normalized:
            style.setdefault("fill", normalized.pop("backgroundColor"))

        if isinstance(properties, dict):
            if "text" in properties and "text" not in normalized:
                normalized["text"] = properties["text"]
            for key in ("fontSize", "fontFamily", "color", "textAlign"):
                if key in properties:
                    style[key] = properties[key]

        asset = normalized.get("asset")
        if (
            isinstance(asset, dict)
            and "placeholderStyle" in asset
            and "placeholderStyle" not in normalized
        ):
            normalized["placeholderStyle"] = asset.pop("placeholderStyle")

        normalized.setdefault("zIndex", 5)
        if style:
            normalized["style"] = style
        normalized = self._normalize_connector(normalized, element_aliases or {})
        normalized = self._normalize_semantic_asset(normalized)
        return normalized

    def _normalize_connector(
        self,
        element: dict[str, Any],
        element_aliases: dict[str, str],
    ) -> dict[str, Any]:
        if element.get("type") != "connector":
            return element

        connector = dict(element.get("connector") or {})
        connector.setdefault("kind", element.get("connectorType") or element.get("kind") or "line")
        connector.setdefault("routing", "straight")

        from_source = self._first_present(
            connector,
            element,
            [
                "from",
                "fromElement",
                "fromElementId",
                "source",
                "sourceElement",
                "sourceElementId",
                "start",
                "startElement",
                "startElementId",
            ],
        )
        to_source = self._first_present(
            connector,
            element,
            [
                "to",
                "toElement",
                "toElementId",
                "target",
                "targetElement",
                "targetElementId",
                "end",
                "endElement",
                "endElementId",
            ],
        )
        from_endpoint = self._normalize_connector_endpoint(
            from_source,
            element_aliases,
            default_anchor="right",
        )
        to_endpoint = self._normalize_connector_endpoint(
            to_source,
            element_aliases,
            default_anchor="left",
        )
        if from_endpoint is not None:
            connector["from"] = from_endpoint
            element["from"] = from_endpoint
        if to_endpoint is not None:
            connector["to"] = to_endpoint
            element["to"] = to_endpoint

        if "label" in element and "content" not in element:
            element["content"] = {"label": element["label"]}
        element["connector"] = connector
        return element

    def _first_present(
        self,
        primary: dict[str, Any],
        secondary: dict[str, Any],
        keys: list[str],
    ) -> Any:
        for key in keys:
            if key in primary:
                return primary[key]
            if key in secondary:
                return secondary[key]
        return None

    def _normalize_connector_endpoint(
        self,
        source: Any,
        element_aliases: dict[str, str],
        *,
        default_anchor: str,
    ) -> dict[str, Any] | None:
        if source is None:
            return None

        if isinstance(source, str):
            element_id = self._resolve_element_alias(source, element_aliases)
            if element_id is None:
                return None
            return {
                "target": {"type": "element", "elementId": element_id},
                "anchor": default_anchor,
            }

        if isinstance(source, dict):
            endpoint = deepcopy(source)
            target = endpoint.get("target")
            if isinstance(target, dict):
                element_id = self._resolve_element_alias(target.get("elementId"), element_aliases)
                if element_id is not None:
                    target["elementId"] = element_id
                return endpoint

            point = endpoint.get("point")
            if isinstance(point, dict) and {"x", "y"}.issubset(point):
                return {
                    "target": {"type": "point", "point": point},
                    "anchor": endpoint.get("anchor"),
                }

            if {"x", "y"}.issubset(endpoint):
                return {
                    "target": {
                        "type": "point",
                        "point": {"x": endpoint["x"], "y": endpoint["y"]},
                    }
                }

            raw_element = (
                endpoint.get("elementId")
                or endpoint.get("id")
                or endpoint.get("name")
                or endpoint.get("element")
                or endpoint.get("label")
            )
            element_id = self._resolve_element_alias(raw_element, element_aliases)
            if element_id is None:
                return None
            return {
                "target": {"type": "element", "elementId": element_id},
                "anchor": endpoint.get("anchor") or default_anchor,
            }

        return None

    def _element_aliases_from_project(self, project: Project) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for scene in project.scenes:
            for element in scene.elements:
                self._register_element_aliases(aliases, element.model_dump(by_alias=True))
        return aliases

    def _register_element_aliases(
        self,
        aliases: dict[str, str],
        element: Any,
    ) -> None:
        if not isinstance(element, dict):
            return
        element_id = element.get("id")
        if not isinstance(element_id, str):
            return

        values = [element_id, element.get("name"), element.get("text"), element.get("label")]
        content = element.get("content")
        if isinstance(content, dict):
            values.extend([content.get("text"), content.get("label"), content.get("alt")])

        for value in values:
            key = self._alias_key(value)
            if key:
                aliases[key] = element_id

    def _resolve_element_alias(
        self,
        value: Any,
        aliases: dict[str, str],
    ) -> str | None:
        key = self._alias_key(value)
        if not key:
            return None
        if key in aliases:
            return aliases[key]

        sorted_aliases = sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True)
        for alias_key, element_id in sorted_aliases:
            if key in alias_key or alias_key in key:
                return element_id
        return None

    def _alias_key(self, value: Any) -> str:
        return (
            str(value or "")
            .strip()
            .replace(" ", "")
            .replace("，", "")
            .replace("。", "")
            .replace("：", "")
            .replace(":", "")
            .lower()
        )

    def _validate_commands_sequentially(
        self,
        commands: list[CanvasCommand],
        project: Project,
    ) -> None:
        current_project = project
        for command in commands:
            validation = self._validator.validate([command], current_project)
            if not validation.ok:
                issue_text = "；".join(
                    f"{issue.path}: {issue.code}: {issue.message}"
                    for issue in validation.issues
                )
                raise ValueError(f"LLM 命令未通过业务校验：{issue_text}")
            if command.type == CommandType.EXPORT_PROJECT:
                continue
            try:
                result = self._executor.execute(command, current_project)
            except ValueError as error:
                raise ValueError(f"LLM 命令执行预检失败：{error}") from error
            current_project = result.project

    def _normalize_semantic_asset(self, element: dict[str, Any]) -> dict[str, Any]:
        """把真实世界物体从普通 shape 升级为可语义渲染的生成素材占位。"""

        if element.get("type") in {"text", "connector"}:
            return element

        name_text = " ".join(
            str(value)
            for value in (
                element.get("name"),
                element.get("text"),
                element.get("label"),
                element.get("content"),
            )
            if value
        ).lower()
        object_kind = self._semantic_asset_kind(name_text)
        if object_kind is None:
            return element

        display_name = element.get("name") or object_kind["label"]
        content = element.get("content") if isinstance(element.get("content"), dict) else {}
        asset = element.get("asset") if isinstance(element.get("asset"), dict) else {}
        subject = element.get("subject") if isinstance(element.get("subject"), dict) else {}
        attributes = object_kind.get("attributes") or {}
        key_features = [object_kind["label"]]
        for values in attributes.values():
            key_features.extend(str(value) for value in values)

        normalized = {
            **element,
            "type": "generated_asset",
            "name": display_name,
            "content": {
                **content,
                "alt": content.get("alt") or display_name,
            },
            "asset": {
                "kind": object_kind.get("assetKind", object_kind["kind"]),
                "status": asset.get("status") or "pending",
                "prompt": asset.get("prompt")
                or f"{display_name}，清晰简洁的画布插画风格，适合演示画布",
                "provider": asset.get("provider")
                or object_kind.get("assetProvider")
                or "mock",
            },
            "subject": {
                **subject,
                object_kind.get("subjectType", object_kind["kind"]): {
                    "category": object_kind["label"],
                    "keyFeatures": key_features,
                    **({"attributes": attributes} if attributes else {}),
                    **({"gender": object_kind["gender"]} if object_kind.get("gender") else {}),
                    **(
                        {"variant": object_kind["renderVariant"]}
                        if object_kind.get("renderVariant")
                        else {}
                    ),
                    "renderKey": object_kind["renderKey"],
                },
            },
            "metadata": {
                **(element.get("metadata") if isinstance(element.get("metadata"), dict) else {}),
                "renderKey": object_kind["renderKey"],
                "renderHint": object_kind["renderHint"],
                "renderMode": object_kind.get("renderMode")
                or ("direct" if object_kind.get("directRender") else "placeholder"),
                **(
                    {"assetProvider": object_kind["assetProvider"]}
                    if object_kind.get("assetProvider")
                    else {}
                ),
                **({"assetPath": object_kind["assetPath"]} if object_kind.get("assetPath") else {}),
                **(
                    {"styleFamily": object_kind["styleFamily"]}
                    if object_kind.get("styleFamily")
                    else {}
                ),
                **(
                    {"renderVariant": object_kind["renderVariant"]}
                    if object_kind.get("renderVariant")
                    else {}
                ),
            },
            "placeholderStyle": element.get("placeholderStyle")
            or {
                "fill": "#ffffff",
                "stroke": "#1f8a5b",
                "strokeWidth": 2,
                "radius": 12,
            },
        }
        normalized.pop("shape", None)
        return normalized

    def _semantic_asset_kind(self, text: str) -> dict[str, Any] | None:
        match = self._render_catalog.resolve(text)
        if match is None:
            return None
        return {
            "kind": match.subject_type,
            "assetKind": match.asset_kind,
            "subjectType": match.subject_type,
            "label": match.display_name,
            "features": [match.display_name],
            "renderKey": match.render_key,
            "renderHint": match.render_key,
            "directRender": match.direct_render,
            "renderMode": "asset" if match.asset_path else (
                "direct" if match.direct_render else "placeholder"
            ),
            "category": match.category,
            "assetProvider": match.asset_provider,
            "assetPath": match.asset_path,
            "styleFamily": match.style_family,
            "attributes": match.attributes or {},
            **({"gender": match.variant} if match.variant else {}),
            **({"renderVariant": match.variant} if match.variant else {}),
        }
        if any(keyword in text for keyword in ("男生", "男孩", "男人", "男性", "boy", "man")):
            return {
                "kind": "character",
                "label": "男生",
                "features": ["短发", "上衣", "人物姿态"],
                "gender": "male",
                "renderHint": "character",
                "renderVariant": "male",
            }
        if any(keyword in text for keyword in ("女生", "女孩", "女人", "女性", "girl", "woman")):
            return {
                "kind": "character",
                "label": "女生",
                "features": ["头发", "裙装", "人物姿态"],
                "gender": "female",
                "renderHint": "character",
                "renderVariant": "female",
            }
        if any(keyword in text for keyword in ("人物", "人像", "人", "person", "character")):
            return {
                "kind": "character",
                "label": "人物",
                "features": ["头部", "身体", "人物姿态"],
                "gender": "neutral",
                "renderHint": "character",
                "renderVariant": "neutral",
            }
        if any(keyword in text for keyword in ("猫", "cat", "小猫")):
            return {
                "kind": "character",
                "label": "猫",
                "features": ["尖耳朵", "尾巴", "胡须"],
                "renderHint": "cat",
            }
        if any(keyword in text for keyword in ("桌", "桌子", "table", "desk")):
            return {
                "kind": "product",
                "label": "桌子",
                "features": ["桌面", "桌腿"],
                "renderHint": "table",
            }
        return None

    def _find_scene_id_by_element(self, project: Project, element_id: str) -> str | None:
        for scene in project.scenes:
            if any(element.id == element_id for element in scene.elements):
                return scene.id
        return None

    def _fallback_or_response(
        self,
        user_input: str,
        project: Project,
        attempts: list[PlannerAttempt],
        token_usage: TokenUsage,
    ) -> CommandPlan:
        reason = self._summarize_failure(attempts)
        notice = f"LLM 暂不可用：{reason}"

        if self._fallback_planner is None:
            return CommandPlan(
                "respond",
                [],
                f"{notice}，未执行任何画布命令，请稍后重试或检查模型配置。",
                notice=notice,
                attempts=attempts,
                token_usage=token_usage,
            )

        fallback = self._fallback_planner.plan(user_input, project)
        fallback_notice = f"{notice}；已降级到本地 Demo Planner"
        return CommandPlan(
            fallback.action,
            fallback.commands,
            fallback.message,
            notice=fallback_notice,
            attempts=attempts,
            token_usage=token_usage.plus(fallback.token_usage),
        )

    def _summarize_failure(self, attempts: list[PlannerAttempt]) -> str:
        if not attempts:
            return "未知错误"

        last_error = attempts[-1].error or "输出未通过校验"
        if "quota" in last_error or "rate_limit" in last_error or "额度" in last_error:
            return "额度不足或调用频率受限"
        if "auth" in last_error or "鉴权" in last_error:
            return "鉴权失败，请检查 API Key"
        if "network" in last_error or "timeout" in last_error or "网络" in last_error:
            return "网络连接或请求超时"
        return last_error

    def _retry_feedback(self, category: str, message: str) -> str:
        return f"LLM 调用失败，错误类型：{category}，错误信息：{message}。请重新尝试。"

    def _looks_actionable(self, user_input: str) -> bool:
        actionable_keywords = [
            "创建",
            "生成",
            "添加",
            "加",
            "改成",
            "修改",
            "删除",
            "删掉",
            "切换",
            "放大",
            "缩小",
            "移动",
            "居中",
            "置顶",
            "置底",
            "导出",
            "保存",
            "设置",
            "项目名称",
            "项目名",
            "旁白",
            "字幕",
        ]
        return any(keyword in user_input for keyword in actionable_keywords)

    def _messages(
        self,
        user_input: str,
        project: Project,
        feedback: list[str],
        resolved_target: ElementCandidate | None = None,
        context: PlanningContext | None = None,
    ) -> list[LLMMessage]:
        conversation = context.conversation if context is not None else None
        user_memory = context.user_memory if context is not None else None
        user_payload = {
            "userInput": user_input,
            "project": self._project_context(project),
            "feedback": feedback,
            "resolvedTarget": resolved_target.model_dump(by_alias=True)
            if resolved_target is not None
            else None,
            "conversationContext": conversation.model_dump(by_alias=True)
            if conversation is not None
            else None,
            "userMemoryContext": user_memory.model_dump(by_alias=True)
            if user_memory is not None
            else None,
        }
        return [
            LLMMessage(role="system", content=self._system_prompt()),
            LLMMessage(
                role="user",
                content=json.dumps(user_payload, ensure_ascii=False, indent=2),
            ),
        ]

    def _project_context(self, project: Project) -> dict[str, Any]:
        active_scene = next(
            scene for scene in project.scenes if scene.id == project.active_scene_id
        )
        return {
            "id": project.id,
            "title": project.title,
            "mode": project.mode,
            "activeSceneId": project.active_scene_id,
            "scenes": [
                {
                    "id": scene.id,
                    "name": scene.name,
                    "order": scene.order,
                    "description": scene.description,
                    "narration": scene.narration,
                    "canvas": scene.canvas.model_dump(by_alias=True),
                    "elements": [
                        element.model_dump(by_alias=True) for element in scene.elements
                    ],
                }
                for scene in sorted(project.scenes, key=lambda item: item.order)
            ],
            "activeScene": {
                "id": active_scene.id,
                "name": active_scene.name,
                "narration": active_scene.narration,
                "canvas": active_scene.canvas.model_dump(by_alias=True),
                "elements": [
                    {
                        "id": element.id,
                        "type": element.type,
                        "name": element.name,
                        "text": element.text,
                        "x": element.x,
                        "y": element.y,
                        "width": element.width,
                        "height": element.height,
                        "zIndex": element.z_index,
                    }
                    for element in active_scene.elements
                ],
            },
        }

    def _system_prompt(self) -> str:
        command_types = ", ".join(command.value for command in CommandType)
        render_catalog = self._render_catalog.prompt_manifest()
        return f"""
Render Catalog（前端本地绘制能力清单）：
{render_catalog}
- direct 对象可以写 metadata.renderKey/renderVariant 让前端本地渲染。
- minio/assetPath 对象只写 metadata.renderKey 和语义属性。
- 不要输出图片 URL，系统会通过后端代理解析素材路径。
- placeholder 对象只能作为 generated_asset 占位等待生成，不要猜成其他 renderKey。
- 用户说法和预存名称不一致时，先按 aliases/variants 归一化。
- 元素可按需写 description，用于展示人物姓名、角色特征、商品口味等人类可读属性；
  没有明确属性时不要编造。
- 口味、颜色、卖点等结构化属性保留在 subject 或 asset.prompt。
- 目录外对象保留原始描述到 asset.prompt。

你是 VoiceCanvas 的画布指令规划器。你只负责把中文用户输入转换成受控 JSON，不能直接覆盖 Project。

必须只返回一个 JSON 对象，格式如下：
{{
  "action": "commands" | "undo" | "redo" | "respond",
  "message": "给用户看的简短中文说明",
  "commands": [
    {{
      "type": "命令类型见支持列表",
      "payload": {{}},
      "reason": "为什么执行这条命令"
    }}
  ]
}}

约束：
- 支持的命令类型：{command_types}。
- action=commands 时 commands 必须至少 1 条；undo、redo、respond 时 commands 必须为空数组。
- 不要输出 id、source、createdAt，系统会补齐。
- 不要编造当前项目不存在的 sceneId 或 elementId。
- 同一批 commands 可以先 ADD_ELEMENT 再用后续 connector 引用前面元素的 name 或 id。
- 新增元素时 element 至少包含 type、x、y、width、height、zIndex。
- 新增或修改元素时，如果用户补充“这个人叫小王”“奶茶是草莓味”等对象属性，
  可写入 element.description 或 UPDATE_ELEMENT.patch.description。
- 文本元素 type 使用 "text"，形状元素 type 使用 "shape"，连接线 type 使用 "connector"。
- 连接线必须提供 connector.from 和 connector.to。
- 也可以用 from/to/source/target 写元素名称，系统会归一化为 elementId。
- connector 示例：
  {{"type":"connector","name":"箭头","from":"小女孩","to":"猫",
    "content":{{"label":"指向"}},"x":0,"y":0,"width":1,"height":1,"zIndex":8}}。
- 用户一句话里有多个对象、文字或指向关系时，要逐项生成命令，不要省略其中任何关系。
- 用户要求“导出项目/保存项目/导出 JSON/导出结构化文件”时，输出 EXPORT_PROJECT，
  payload 使用 {{"format":"json","scope":"project"}}。
- 用户要求“导出图片/保存当前画面/导出当前分镜图片”时，输出 EXPORT_PROJECT，
  payload 使用 {{"format":"png","scope":"active_scene"}}。
- 画真实世界物体，例如猫、人物、桌子、产品、背景时，优先使用 type="generated_asset"。
- generated_asset 必须包含 asset.kind、asset.status="pending"、asset.prompt 和 placeholderStyle。
- 不确定用户目标时返回 respond，并在 message 中说明需要用户补充什么。
- 删除、修改、切换必须优先使用上下文中已有的 sceneId/elementId。
- 用户要求修改项目名称时，输出 UPDATE_PROJECT，payload 使用 {{"patch":{{"title":"新名称"}}}}。
- 用户要求修改某个镜头/画布/分镜的旁白、字幕或旁白字幕时，输出 UPDATE_SCENE，
  payload.patch.narration 写入用户给出的旁白文本；未指定镜头时使用 activeSceneId。

比赛 Demo 默认策略：
- 用户要求“创建/生成三镜头带货分镜”时，不要询问细节；使用合理默认结构：
  第一镜头主图开场，第二镜头产品特写，第三镜头下单转化。
- 可以先 UPDATE_SCENE 修改已有空白镜头，再用 CREATE_SCENE 创建后续镜头。
- 后续新镜头如需元素，请在 CREATE_SCENE.payload.scene.elements 中直接内嵌。
- 用户要求“加标题，写...”时，在 activeSceneId 添加 text 元素。
- 用户要求“把标题改成...”时，查找当前 activeScene 中名称或文本像标题的 text 元素并更新。
- 如果输入里已经有 resolvedTarget，修改/删除/移动等操作必须使用其中的 sceneId 和 elementId。
- 如果输入里有 conversationContext，优先把 focusStack 作为
  “它、这个、刚才那个、往左移一点”等省略表达的近期语境。
- recentTurns 只用于理解最近对话，不要把已过期或不存在的元素编造成可操作对象。
- 如果输入里有 userMemoryContext，把 relevant 里的 active 长期记忆作为偏好、工作流和负向约束参考；
  当前用户指令、项目状态、澄清回答和显式目标优先级更高，不要执行与本轮请求无关的记忆。
""".strip()

    def _extract_json(self, raw_output: str) -> str:
        text = raw_output.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("LLM 输出中没有可解析的 JSON 对象")
        return text[start : end + 1]
