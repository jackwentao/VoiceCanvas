from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from voicecanvas.application.command_executor import CommandExecutor
from voicecanvas.application.command_validator import CommandValidator
from voicecanvas.application.demo_command_planner import DemoCommandPlanner
from voicecanvas.application.history_manager import HistoryManager
from voicecanvas.application.project_repository import InMemoryProjectRepository
from voicecanvas.domain.history import HistoryEntry
from voicecanvas.domain.patches import CanvasPatch
from voicecanvas.domain.project import Project


class TurnSummary(BaseModel):
    completed: bool
    message: str
    command_count: int = Field(alias="commandCount")

    model_config = {"populate_by_name": True}


class OrchestrationServiceResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    status: Literal["COMPLETED", "FAILED"]
    stage: Literal["completed", "failed"]
    project: Project
    patches: list[CanvasPatch]
    history: list[HistoryEntry]
    events: list[dict[str, Any]]
    summary: TurnSummary
    next_action: dict[str, Any] | None = Field(default=None, alias="nextAction")

    model_config = {"populate_by_name": True}


class OrchestrationService:
    """同步编排 Demo 指令，并执行真实后端命令闭环。"""

    def __init__(
        self,
        repository: InMemoryProjectRepository | None = None,
        planner: DemoCommandPlanner | None = None,
        executor: CommandExecutor | None = None,
        validator: CommandValidator | None = None,
    ) -> None:
        self._repository = repository or InMemoryProjectRepository()
        self._planner = planner or DemoCommandPlanner()
        self._validator = validator or CommandValidator()
        self._executor = executor or CommandExecutor(self._validator)
        self._histories: dict[str, HistoryManager] = {}

    def handle_user_input(self, project_id: str, user_input: str) -> OrchestrationServiceResponse:
        session_id = f"session_{uuid4().hex[:12]}"
        project = self._repository.get_or_create(project_id)
        history = self._history_for(project.id)
        events = [
            self._stage_event(session_id, "understanding", "正在理解用户输入"),
        ]
        plan = self._planner.plan(user_input, project)

        if plan.action == "respond":
            summary = TurnSummary(completed=True, message=plan.message, commandCount=0)
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
                message=result.failed.error,
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
            message=f"已执行 {len(result.applied)} 条命令",
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
        status: Literal["COMPLETED", "FAILED"],
        project: Project,
        patches: list[CanvasPatch],
        history: list[HistoryEntry],
        events: list[dict[str, Any]],
        summary: TurnSummary,
    ) -> OrchestrationServiceResponse:
        return OrchestrationServiceResponse(
            sessionId=session_id,
            status=status,
            stage="completed" if status == "COMPLETED" else "failed",
            project=project,
            patches=patches,
            history=history,
            events=events,
            summary=summary,
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

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
