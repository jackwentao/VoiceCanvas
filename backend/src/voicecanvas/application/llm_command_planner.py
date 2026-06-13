import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError, model_validator

from voicecanvas.adapters.llm.base import LLMClient, LLMClientError, LLMMessage
from voicecanvas.application.command_planner import CommandPlan, CommandPlanner, PlannerAttempt
from voicecanvas.application.command_validator import CommandValidator
from voicecanvas.application.referent_resolver import (
    ElementCandidate,
    ReferentResolver,
    resolution_to_next_action,
)
from voicecanvas.domain.commands import CanvasCommand, CommandType
from voicecanvas.domain.project import Project


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
        max_attempts: int = 3,
        temperature: float = 0.1,
        timeout_seconds: float = 20,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts 必须大于等于 1")
        self._client = client
        self._fallback_planner = fallback_planner
        self._validator = validator or CommandValidator()
        self._referent_resolver = referent_resolver or ReferentResolver()
        self._max_attempts = max_attempts
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds

    def plan(self, user_input: str, project: Project) -> CommandPlan:
        attempts: list[PlannerAttempt] = []
        feedback: list[str] = []
        resolved_target = self._resolve_referent_before_llm(user_input, project)
        if isinstance(resolved_target, CommandPlan):
            return resolved_target

        for attempt_index in range(1, self._max_attempts + 1):
            raw_output: str | None = None
            try:
                completion = self._client.complete_json(
                    self._messages(user_input, project, feedback, resolved_target),
                    temperature=self._temperature,
                    timeout_seconds=self._timeout_seconds,
                )
                raw_output = completion.content
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

        return self._fallback_or_response(user_input, project, attempts)

    def _resolve_referent_before_llm(
        self,
        user_input: str,
        project: Project,
    ) -> ElementCandidate | CommandPlan | None:
        resolution = self._referent_resolver.resolve(user_input, project)
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
        for index, draft in enumerate(output.commands):
            for command_type, payload, reason in self._normalize_draft(draft, project, index):
                commands.append(
                    CanvasCommand(
                        id=f"cmd_{uuid4().hex[:12]}",
                        type=command_type,
                        source="ai",
                        payload=payload,
                        reason=reason,
                        createdAt=datetime.now(UTC).isoformat(),
                    )
                )
        validation = self._validator.validate(commands, project)
        if not validation.ok:
            issue_text = "；".join(
                f"{issue.path}: {issue.code}: {issue.message}" for issue in validation.issues
            )
            raise ValueError(f"LLM 命令未通过业务校验：{issue_text}")

        return CommandPlan("commands", commands, output.message, attempts=attempts)

    def _normalize_draft(
        self,
        draft: LLMCommandDraft,
        project: Project,
        index: int,
    ) -> list[tuple[CommandType, dict[str, Any], str | None]]:
        payload = deepcopy(draft.payload)

        if draft.type == CommandType.ADD_ELEMENT:
            payload.setdefault("sceneId", project.active_scene_id)
            if isinstance(payload.get("element"), dict):
                payload["element"] = self._normalize_element(payload["element"])
            return [(draft.type, payload, draft.reason)]

        if draft.type == CommandType.CREATE_SCENE:
            if isinstance(payload.get("scene"), dict):
                next_order = max(scene.order for scene in project.scenes) + index + 1
                payload["scene"] = self._normalize_scene(payload["scene"], next_order)
            return [(draft.type, payload, draft.reason)]

        if draft.type == CommandType.UPDATE_SCENE:
            return self._normalize_update_scene(draft, payload, project)

        if draft.type == CommandType.UPDATE_ELEMENT:
            return [
                (
                    draft.type,
                    self._normalize_update_element_payload(payload, project),
                    draft.reason,
                )
            ]

        return [(draft.type, payload, draft.reason)]

    def _normalize_update_scene(
        self,
        draft: LLMCommandDraft,
        payload: dict[str, Any],
        project: Project,
    ) -> list[tuple[CommandType, dict[str, Any], str | None]]:
        if "sceneId" in payload and isinstance(payload.get("patch"), dict):
            return self._normalize_scene_patch_with_elements(draft, payload)

        scene = payload.get("scene")
        if not isinstance(scene, dict):
            return [(draft.type, payload, draft.reason)]

        commands: list[tuple[CommandType, dict[str, Any], str | None]] = []
        patch = {
            key: scene[key]
            for key in ("name", "description", "canvas")
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
                    commands.append(
                        (
                            CommandType.ADD_ELEMENT,
                            {
                                "sceneId": project.active_scene_id,
                                "element": self._normalize_element(element),
                            },
                            "补充镜头元素",
                        )
                    )

        return commands or [(draft.type, payload, draft.reason)]

    def _normalize_scene_patch_with_elements(
        self,
        draft: LLMCommandDraft,
        payload: dict[str, Any],
    ) -> list[tuple[CommandType, dict[str, Any], str | None]]:
        scene_id = payload["sceneId"]
        source_patch = deepcopy(payload["patch"])
        elements = source_patch.pop("elements", None)
        patch = {
            key: source_patch[key]
            for key in ("name", "description", "canvas")
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
                    commands.append(
                        (
                            CommandType.ADD_ELEMENT,
                            {
                                "sceneId": scene_id,
                                "element": self._normalize_element(element),
                            },
                            "补充镜头元素",
                        )
                    )

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

    def _normalize_scene(self, scene: dict[str, Any], order: int) -> dict[str, Any]:
        normalized = deepcopy(scene)
        normalized.setdefault("id", f"scene_ai_{uuid4().hex[:12]}")
        normalized.setdefault("order", order)
        elements = normalized.get("elements")
        if isinstance(elements, list):
            normalized["elements"] = [
                self._normalize_element(element, require_id=True)
                for element in elements
                if isinstance(element, dict)
            ]
        return normalized

    def _normalize_element(
        self,
        element: dict[str, Any],
        *,
        require_id: bool = False,
    ) -> dict[str, Any]:
        normalized = deepcopy(element)
        properties = normalized.pop("properties", None)
        style = dict(normalized.get("style") or {})

        if require_id:
            normalized.setdefault("id", f"el_ai_{uuid4().hex[:12]}")
        if "content" in normalized and "text" not in normalized:
            normalized["text"] = normalized.pop("content")
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

        normalized.setdefault("zIndex", 5)
        if style:
            normalized["style"] = style
        return normalized

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
            )

        fallback = self._fallback_planner.plan(user_input, project)
        fallback_notice = f"{notice}；已降级到本地 Demo Planner"
        return CommandPlan(
            fallback.action,
            fallback.commands,
            fallback.message,
            notice=fallback_notice,
            attempts=attempts,
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
        ]
        return any(keyword in user_input for keyword in actionable_keywords)

    def _messages(
        self,
        user_input: str,
        project: Project,
        feedback: list[str],
        resolved_target: ElementCandidate | None = None,
    ) -> list[LLMMessage]:
        user_payload = {
            "userInput": user_input,
            "project": self._project_context(project),
            "feedback": feedback,
            "resolvedTarget": resolved_target.model_dump(by_alias=True)
            if resolved_target is not None
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
        return f"""
你是 VoiceCanvas 的画布指令规划器。你只负责把中文用户输入转换成受控 JSON，不能直接覆盖 Project。

必须只返回一个 JSON 对象，格式如下：
{{
  "action": "commands" | "undo" | "redo" | "respond",
  "message": "给用户看的简短中文说明",
  "commands": [
    {{
      "type": "CREATE_SCENE | UPDATE_SCENE | DELETE_SCENE | SWITCH_SCENE | ADD_ELEMENT",
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
- 同一批 commands 不能引用本批刚创建的 sceneId 或 elementId。
- 新增元素时 element 至少包含 type、x、y、width、height、zIndex。
- 文本元素 type 使用 "text"，形状元素 type 使用 "shape"，连接线 type 使用 "connector"。
- 不确定用户目标时返回 respond，并在 message 中说明需要用户补充什么。
- 删除、修改、切换必须优先使用上下文中已有的 sceneId/elementId。

比赛 Demo 默认策略：
- 用户要求“创建/生成三镜头带货分镜”时，不要询问细节；使用合理默认结构：
  第一镜头主图开场，第二镜头产品特写，第三镜头下单转化。
- 可以先 UPDATE_SCENE 修改已有空白镜头，再用 CREATE_SCENE 创建后续镜头。
- 后续新镜头如需元素，请在 CREATE_SCENE.payload.scene.elements 中直接内嵌。
- 用户要求“加标题，写...”时，在 activeSceneId 添加 text 元素。
- 用户要求“把标题改成...”时，查找当前 activeScene 中名称或文本像标题的 text 元素并更新。
- 如果输入里已经有 resolvedTarget，修改/删除/移动等操作必须使用其中的 sceneId 和 elementId。
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
