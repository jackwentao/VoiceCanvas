from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from voicecanvas.application.command_executor import CommandExecutor
from voicecanvas.application.command_planner import CommandPlanner
from voicecanvas.application.command_validator import CommandValidator
from voicecanvas.application.demo_command_planner import DemoCommandPlanner
from voicecanvas.application.history_manager import HistoryManager
from voicecanvas.application.project_repository import InMemoryProjectRepository
from voicecanvas.domain.commands import CanvasCommand, CommandType
from voicecanvas.domain.history import HistoryEntry
from voicecanvas.domain.patches import CanvasPatch
from voicecanvas.domain.project import CanvasElement, Project, Scene


class TurnSummary(BaseModel):
    completed: bool
    message: str
    command_count: int = Field(alias="commandCount")

    model_config = {"populate_by_name": True}


class OrchestrationServiceResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    status: Literal["COMPLETED", "FAILED", "WAITING_FOR_USER"]
    stage: Literal["completed", "failed", "waiting_for_user"]
    project: Project
    patches: list[CanvasPatch]
    history: list[HistoryEntry]
    events: list[dict[str, Any]]
    summary: TurnSummary
    next_action: dict[str, Any] | None = Field(default=None, alias="nextAction")

    model_config = {"populate_by_name": True}


class ProjectState(BaseModel):
    project: Project
    history: list[HistoryEntry]
    events: list[dict[str, Any]] = Field(default_factory=list)


class OrchestrationService:
    """同步编排 Demo 指令，并执行真实后端命令闭环。"""

    def __init__(
        self,
        repository: InMemoryProjectRepository | None = None,
        planner: CommandPlanner | None = None,
        executor: CommandExecutor | None = None,
        validator: CommandValidator | None = None,
    ) -> None:
        self._repository = repository or InMemoryProjectRepository()
        self._planner = planner or DemoCommandPlanner()
        self._validator = validator or CommandValidator()
        self._executor = executor or CommandExecutor(self._validator)
        self._histories: dict[str, HistoryManager] = {}
        self._pending_clarifications: dict[str, dict[str, Any]] = {}

    def handle_user_input(self, project_id: str, user_input: str) -> OrchestrationServiceResponse:
        session_id = f"session_{uuid4().hex[:12]}"
        project = self._repository.get_or_create(project_id)
        history = self._history_for(project.id)
        events = [
            self._stage_event(session_id, "understanding", "正在理解用户输入"),
        ]
        if self._is_clear_scene_request(user_input):
            next_action = self._next_action_with_session_id(
                self._clear_scene_next_action(project.active_scene_id),
                session_id,
            )
            self._pending_clarifications[session_id] = {
                "projectId": project.id,
                "originalInput": user_input,
                "nextAction": deepcopy(next_action),
            }
            message = "清空当前画布会删除当前镜头里的所有元素，请确认是否继续"
            events.append(self._clarification_event(session_id, next_action, message))
            summary = TurnSummary(completed=False, message=message, commandCount=0)
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "WAITING_FOR_USER",
                project,
                [],
                history.entries(),
                events,
                summary,
                next_action=next_action,
            )

        plan = self._planner.plan(user_input, project)
        if plan.notice:
            events.append(self._planner_warning_event(session_id, plan.notice))

        if plan.action == "ask_clarification":
            next_action = self._next_action_with_session_id(plan.next_action, session_id)
            self._pending_clarifications[session_id] = {
                "projectId": project.id,
                "originalInput": user_input,
                "nextAction": deepcopy(next_action),
            }
            events.append(self._clarification_event(session_id, next_action, plan.message))
            summary = TurnSummary(completed=False, message=plan.message, commandCount=0)
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "WAITING_FOR_USER",
                project,
                [],
                history.entries(),
                events,
                summary,
                next_action=next_action,
            )

        if plan.action == "respond":
            summary = TurnSummary(
                completed=True,
                message=self._message_with_notice(plan.message, plan.notice),
                commandCount=0,
            )
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "COMPLETED",
                project,
                [],
                history.entries(),
                events,
                summary,
            )

        if plan.action == "undo":
            return self._undo(session_id, project, history, events)

        if plan.action == "redo":
            return self._redo(session_id, project, history, events)

        events.append(self._stage_event(session_id, "executing", "正在执行画布命令"))
        validation = self._validator.validate(plan.commands, project)
        if not validation.ok:
            message = "；".join(issue.message for issue in validation.issues)
            summary = TurnSummary(
                completed=False,
                message=self._message_with_notice(message, plan.notice),
                commandCount=0,
            )
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "FAILED",
                project,
                [],
                history.entries(),
                events,
                summary,
            )

        result = self._executor.execute_batch(plan.commands, project)
        for applied in result.applied:
            history.record(applied.history_entry)
            events.extend(
                self._patch_event(session_id, patch, applied.command_id)
                for patch in applied.patches
            )

        self._repository.save(result.project)
        if result.failed is not None:
            summary = TurnSummary(
                completed=False,
                message=self._message_with_notice(result.failed.error, plan.notice),
                commandCount=len(result.applied),
            )
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "FAILED",
                result.project,
                self._collect_patches(result.applied),
                history.entries(),
                events,
                summary,
            )

        summary = TurnSummary(
            completed=True,
            message=self._message_with_notice(
                f"已执行 {len(result.applied)} 条命令",
                plan.notice,
            ),
            commandCount=len(result.applied),
        )
        events.append(self._turn_summary_event(session_id, summary))
        return self._response(
            session_id,
            "COMPLETED",
            result.project,
            self._collect_patches(result.applied),
            history.entries(),
            events,
            summary,
        )

    def resume_user_input(
        self, project_id: str, session_id: str, user_input: str
    ) -> OrchestrationServiceResponse:
        """用用户的澄清回答恢复上一轮挂起任务。"""

        project = self._repository.get_or_create(project_id)
        history = self._history_for(project.id)
        events = [self._stage_event(session_id, "understanding", "正在解析澄清回答")]
        pending = self._pending_clarifications.get(session_id)
        if not pending:
            summary = TurnSummary(completed=False, message="没有可恢复的澄清任务", commandCount=0)
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "FAILED",
                project,
                [],
                history.entries(),
                events,
                summary,
            )

        if self._is_clear_scene_confirmation(pending):
            return self._resume_clear_scene_confirmation(
                project, history, events, pending, session_id, user_input
            )

        selected = self._resolve_clarification_answer(
            user_input, pending["nextAction"].get("options", [])
        )
        if selected is None:
            next_action = self._next_action_with_session_id(pending["nextAction"], session_id)
            message = "我还不能确定你指的是哪一个，请换一种说法"
            events.append(self._clarification_event(session_id, next_action, message))
            summary = TurnSummary(completed=False, message=message, commandCount=0)
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "WAITING_FOR_USER",
                project,
                [],
                history.entries(),
                events,
                summary,
                next_action=next_action,
            )

        command = self._command_from_pending_clarification(project, pending, selected)
        if command is None:
            summary = TurnSummary(completed=False, message="澄清目标已不存在", commandCount=0)
            events.append(self._turn_summary_event(session_id, summary))
            self._pending_clarifications.pop(session_id, None)
            return self._response(
                session_id,
                "FAILED",
                project,
                [],
                history.entries(),
                events,
                summary,
            )

        self._pending_clarifications.pop(session_id, None)
        events.append(self._stage_event(session_id, "executing", "正在恢复并执行上一轮任务"))
        validation = self._validator.validate([command], project)
        if not validation.ok:
            message = "；".join(issue.message for issue in validation.issues)
            summary = TurnSummary(completed=False, message=message, commandCount=0)
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "FAILED",
                project,
                [],
                history.entries(),
                events,
                summary,
            )

        result = self._executor.execute_batch([command], project)
        for applied in result.applied:
            history.record(applied.history_entry)
            events.extend(
                self._patch_event(session_id, patch, applied.command_id)
                for patch in applied.patches
            )
        self._repository.save(result.project)
        message = f"已根据澄清回答修改 {selected.get('label') or selected.get('elementId')}"
        summary = TurnSummary(completed=True, message=message, commandCount=len(result.applied))
        events.append(self._turn_summary_event(session_id, summary))
        return self._response(
            session_id,
            "COMPLETED",
            result.project,
            self._collect_patches(result.applied),
            history.entries(),
            events,
            summary,
        )

    def _resume_clear_scene_confirmation(
        self,
        project: Project,
        history: HistoryManager,
        events: list[dict[str, Any]],
        pending: dict[str, Any],
        session_id: str,
        user_input: str,
    ) -> OrchestrationServiceResponse:
        answer = self._resolve_confirmation_answer(user_input)
        if answer is None:
            next_action = self._next_action_with_session_id(pending["nextAction"], session_id)
            message = "请说确认清空，或说取消"
            events.append(self._clarification_event(session_id, next_action, message))
            summary = TurnSummary(completed=False, message=message, commandCount=0)
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "WAITING_FOR_USER",
                project,
                [],
                history.entries(),
                events,
                summary,
                next_action=next_action,
            )

        self._pending_clarifications.pop(session_id, None)
        if answer is False:
            summary = TurnSummary(completed=True, message="已取消清空画布", commandCount=0)
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "COMPLETED",
                project,
                [],
                history.entries(),
                events,
                summary,
            )

        resume_with = pending["nextAction"].get("resumePolicy", {}).get("resumeWith", {})
        scene_id = resume_with.get("sceneId") or project.active_scene_id
        command = self._canvas_command(
            CommandType.CLEAR_SCENE,
            {"sceneId": scene_id},
            "用户确认后清空当前画布",
        )
        events.append(self._stage_event(session_id, "executing", "正在清空当前画布"))
        validation = self._validator.validate([command], project)
        if not validation.ok:
            message = "；".join(issue.message for issue in validation.issues)
            summary = TurnSummary(completed=False, message=message, commandCount=0)
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "FAILED",
                project,
                [],
                history.entries(),
                events,
                summary,
            )

        result = self._executor.execute_batch([command], project)
        for applied in result.applied:
            history.record(applied.history_entry)
            events.extend(
                self._patch_event(session_id, patch, applied.command_id)
                for patch in applied.patches
            )
        self._repository.save(result.project)
        summary = TurnSummary(completed=True, message="已清空当前画布", commandCount=1)
        events.append(self._turn_summary_event(session_id, summary))
        return self._response(
            session_id,
            "COMPLETED",
            result.project,
            self._collect_patches(result.applied),
            history.entries(),
            events,
            summary,
        )

    def get_project_state(self, project_id: str) -> ProjectState:
        project = self._repository.get_or_create(project_id)
        history = self._history_for(project.id)
        return ProjectState(project=project, history=history.entries(), events=[])

    def _undo(
        self,
        session_id: str,
        project: Project,
        history: HistoryManager,
        events: list[dict[str, Any]],
    ) -> OrchestrationServiceResponse:
        events.append(self._stage_event(session_id, "executing", "正在撤销上一步操作"))
        try:
            result = history.undo(project, self._executor.apply_without_recording)
        except ValueError as error:
            summary = TurnSummary(completed=False, message=str(error), commandCount=0)
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "FAILED",
                project,
                [],
                history.entries(),
                events,
                summary,
            )

        self._repository.save(result.project)
        events.extend(
            self._patch_event(session_id, patch, result.history_entry.command.id)
            for patch in result.patches
        )
        summary = TurnSummary(completed=True, message="已撤销上一步操作", commandCount=1)
        events.append(self._turn_summary_event(session_id, summary))
        return self._response(
            session_id,
            "COMPLETED",
            result.project,
            result.patches,
            history.entries(),
            events,
            summary,
        )

    def _redo(
        self,
        session_id: str,
        project: Project,
        history: HistoryManager,
        events: list[dict[str, Any]],
    ) -> OrchestrationServiceResponse:
        events.append(self._stage_event(session_id, "executing", "正在重做上一步操作"))
        try:
            result = history.redo(project, self._executor.apply_without_recording)
        except ValueError as error:
            summary = TurnSummary(completed=False, message=str(error), commandCount=0)
            events.append(self._turn_summary_event(session_id, summary))
            return self._response(
                session_id,
                "FAILED",
                project,
                [],
                history.entries(),
                events,
                summary,
            )

        self._repository.save(result.project)
        events.extend(
            self._patch_event(session_id, patch, result.history_entry.command.id)
            for patch in result.patches
        )
        summary = TurnSummary(completed=True, message="已重做上一步操作", commandCount=1)
        events.append(self._turn_summary_event(session_id, summary))
        return self._response(
            session_id,
            "COMPLETED",
            result.project,
            result.patches,
            history.entries(),
            events,
            summary,
        )

    def _response(
        self,
        session_id: str,
        status: Literal["COMPLETED", "FAILED", "WAITING_FOR_USER"],
        project: Project,
        patches: list[CanvasPatch],
        history: list[HistoryEntry],
        events: list[dict[str, Any]],
        summary: TurnSummary,
        next_action: dict[str, Any] | None = None,
    ) -> OrchestrationServiceResponse:
        return OrchestrationServiceResponse(
            sessionId=session_id,
            status=status,
            stage=self._stage_from_status(status),
            project=project,
            patches=patches,
            history=history,
            events=events,
            summary=summary,
            nextAction=next_action,
        )

    def _history_for(self, project_id: str) -> HistoryManager:
        if project_id not in self._histories:
            self._histories[project_id] = HistoryManager()
        return self._histories[project_id]

    def _collect_patches(self, applied: list[Any]) -> list[CanvasPatch]:
        return [patch for result in applied for patch in result.patches]

    def _stage_event(self, session_id: str, stage: str, message: str) -> dict[str, Any]:
        return {
            "type": "STAGE_CHANGED",
            "sessionId": session_id,
            "stage": stage,
            "message": message,
            "createdAt": self._now(),
        }

    def _patch_event(
        self, session_id: str, patch: CanvasPatch, command_id: str
    ) -> dict[str, Any]:
        return {
            "type": "CANVAS_PATCH_APPLIED",
            "sessionId": session_id,
            "commandId": command_id,
            "patch": patch.model_dump(by_alias=True),
            "createdAt": self._now(),
        }

    def _turn_summary_event(self, session_id: str, summary: TurnSummary) -> dict[str, Any]:
        return {
            "type": "TURN_SUMMARY",
            "sessionId": session_id,
            "summary": summary.model_dump(by_alias=True),
            "createdAt": self._now(),
        }

    def _clarification_event(
        self,
        session_id: str,
        next_action: dict[str, Any] | None,
        message: str,
    ) -> dict[str, Any]:
        return {
            "type": "CLARIFICATION_REQUESTED",
            "sessionId": session_id,
            "question": next_action.get("question", message) if next_action else message,
            "options": next_action.get("options", []) if next_action else [],
            "createdAt": self._now(),
        }

    def _planner_warning_event(self, session_id: str, notice: str) -> dict[str, Any]:
        return {
            "type": "PLANNER_WARNING",
            "sessionId": session_id,
            "message": notice,
            "createdAt": self._now(),
        }

    def _message_with_notice(self, message: str, notice: str | None) -> str:
        return f"{notice}；{message}" if notice else message

    def _stage_from_status(
        self, status: Literal["COMPLETED", "FAILED", "WAITING_FOR_USER"]
    ) -> Literal["completed", "failed", "waiting_for_user"]:
        if status == "COMPLETED":
            return "completed"
        if status == "WAITING_FOR_USER":
            return "waiting_for_user"
        return "failed"

    def _next_action_with_session_id(
        self,
        next_action: dict[str, Any] | None,
        session_id: str,
    ) -> dict[str, Any] | None:
        if next_action is None:
            return None
        updated = deepcopy(next_action)
        resume_policy = updated.setdefault("resumePolicy", {})
        resume_policy["sessionId"] = session_id
        return updated

    def _resolve_clarification_answer(
        self, answer: str, options: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        normalized_answer = self._normalize_answer(answer)
        if not normalized_answer or not options:
            return None

        for option in options:
            values = [
                option.get("id"),
                option.get("value"),
                option.get("label"),
                option.get("elementId"),
            ]
            normalized_values = [self._normalize_answer(value) for value in values if value]
            if any(
                value in normalized_answer or normalized_answer in value
                for value in normalized_values
            ):
                return option

        ordinal = self._ordinal_index_from_answer(normalized_answer)
        if ordinal is not None and ordinal < len(options):
            return options[ordinal]

        if "左" in normalized_answer:
            return self._extreme_option(options, "x", min)
        if "右" in normalized_answer:
            return self._extreme_option(options, "x", max)
        if "上" in normalized_answer:
            return self._extreme_option(options, "y", min)
        if "下" in normalized_answer:
            return self._extreme_option(options, "y", max)
        if "大" in normalized_answer:
            return self._area_option(options, max)
        if "小" in normalized_answer:
            return self._area_option(options, min)
        return None

    def _is_clear_scene_confirmation(self, pending: dict[str, Any]) -> bool:
        next_action = pending.get("nextAction", {})
        resume_with = next_action.get("resumePolicy", {}).get("resumeWith", {})
        return (
            next_action.get("type") == "CONFIRM_CLEAR_SCENE"
            or resume_with.get("type") == "CLEAR_SCENE_CONFIRMATION"
        )

    def _is_clear_scene_request(self, text: str) -> bool:
        normalized = self._normalize_answer(text)
        return any(
            keyword in normalized
            for keyword in [
                "清空画布",
                "清空当前画布",
                "清空当前镜头",
                "删除所有元素",
                "删掉所有元素",
                "全部清空",
                "重新开始这个画布",
            ]
        )

    def _clear_scene_next_action(self, scene_id: str) -> dict[str, Any]:
        return {
            "id": f"clarification_{uuid4().hex[:12]}",
            "type": "CONFIRM_CLEAR_SCENE",
            "question": "清空当前画布会删除所有元素。请说确认清空，或说取消。",
            "expectedAnswerType": "confirmation",
            "options": [
                {"id": "confirm", "label": "确认清空", "value": "confirm"},
                {"id": "cancel", "label": "取消", "value": "cancel"},
            ],
            "resumePolicy": {
                "allowVoiceAnswer": True,
                "resumeWith": {
                    "type": "CLEAR_SCENE_CONFIRMATION",
                    "sceneId": scene_id,
                },
            },
        }

    def _resolve_confirmation_answer(self, answer: str) -> bool | None:
        normalized = self._normalize_answer(answer)
        cancel_words = ["取消", "不清空", "不要清空", "别清空", "算了", "不用", "否", "不"]
        if any(word in normalized for word in cancel_words):
            return False

        confirm_words = ["确认清空", "确认", "确定", "清空", "继续", "执行", "是", "好"]
        if any(word in normalized for word in confirm_words):
            return True
        return None

    def _command_from_pending_clarification(
        self,
        project: Project,
        pending: dict[str, Any],
        selected: dict[str, Any],
    ) -> CanvasCommand | None:
        scene_id = selected.get("sceneId")
        element_id = selected.get("elementId") or selected.get("value") or selected.get("id")
        target = self._find_element_by_id(project, scene_id, element_id)
        if target is None:
            return None

        scene, element = target
        original_input = str(pending.get("originalInput", ""))
        if any(keyword in original_input for keyword in ["删除", "删掉", "不要"]):
            return self._canvas_command(
                CommandType.DELETE_ELEMENT,
                {"sceneId": scene.id, "elementId": element.id},
                "根据澄清结果删除元素",
            )

        if any(keyword in original_input for keyword in ["放大", "变大", "大一点"]):
            return self._canvas_command(
                CommandType.UPDATE_ELEMENT,
                {
                    "sceneId": scene.id,
                    "elementId": element.id,
                    "patch": {
                        "width": round(element.width * 1.15, 2),
                        "height": round(element.height * 1.15, 2),
                    },
                },
                "根据澄清结果放大元素",
            )

        return self._canvas_command(
            CommandType.UPDATE_ELEMENT,
            {
                "sceneId": scene.id,
                "elementId": element.id,
                "patch": {"y": 36, "zIndex": 8},
            },
            "根据澄清结果移动元素",
        )

    def _find_element_by_id(
        self, project: Project, scene_id: str | None, element_id: str | None
    ) -> tuple[Scene, CanvasElement] | None:
        if not element_id:
            return None
        scenes = (
            [scene for scene in project.scenes if scene.id == scene_id]
            if scene_id
            else project.scenes
        )
        for scene in scenes:
            for element in scene.elements:
                if element.id == element_id:
                    return scene, element
        return None

    def _canvas_command(
        self, command_type: CommandType, payload: dict[str, Any], reason: str
    ) -> CanvasCommand:
        return CanvasCommand(
            id=f"cmd_{uuid4().hex[:12]}",
            type=command_type,
            source="ai",
            payload=payload,
            reason=reason,
            createdAt=self._now(),
        )

    def _normalize_answer(self, value: object) -> str:
        return (
            str(value or "")
            .strip()
            .replace(" ", "")
            .replace("，", "")
            .replace("。", "")
            .lower()
        )

    def _ordinal_index_from_answer(self, answer: str) -> int | None:
        pairs = [
            (0, ["第一个", "第一", "一个", "1", "一号"]),
            (1, ["第二个", "第二", "2", "二号"]),
            (2, ["第三个", "第三", "3", "三号"]),
            (3, ["第四个", "第四", "4", "四号"]),
        ]
        for index, keywords in pairs:
            if any(keyword in answer for keyword in keywords):
                return index
        return None

    def _extreme_option(
        self,
        options: list[dict[str, Any]],
        axis: str,
        chooser: Any,
    ) -> dict[str, Any] | None:
        with_bounds = [
            option for option in options if isinstance(option.get("bounds"), dict)
        ]
        if not with_bounds:
            return None
        return chooser(
            with_bounds,
            key=lambda option: float(option["bounds"].get(axis, 0)),
        )

    def _area_option(
        self, options: list[dict[str, Any]], chooser: Any
    ) -> dict[str, Any] | None:
        with_bounds = [
            option for option in options if isinstance(option.get("bounds"), dict)
        ]
        if not with_bounds:
            return None
        return chooser(
            with_bounds,
            key=lambda option: float(option["bounds"].get("width", 0))
            * float(option["bounds"].get("height", 0)),
        )

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
