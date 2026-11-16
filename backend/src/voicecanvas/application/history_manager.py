from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from voicecanvas.domain.commands import CanvasCommand
from voicecanvas.domain.history import HistoryEntry, HistoryStatus, UndoRedoState
from voicecanvas.domain.patches import CanvasPatch
from voicecanvas.domain.project import Project


@dataclass
class HistoryOperationResult:
    project: Project
    patches: list[CanvasPatch]
    history_entry: HistoryEntry


class HistoryManager:
    """维护画布操作历史，并把 undo/redo 交给同一套命令执行逻辑。"""

    def __init__(self) -> None:
        self._undo_stack: list[HistoryEntry] = []
        self._redo_stack: list[HistoryEntry] = []

    def record(self, entry: HistoryEntry) -> None:
        self._undo_stack.append(entry)
        self._redo_stack.clear()

    def undo(
        self,
        project: Project,
        apply_command: Callable[[CanvasCommand, Project], Any],
    ) -> HistoryOperationResult:
        if not self._undo_stack:
            raise ValueError("没有可以撤销的操作")

        entry = self._undo_stack.pop()
        if entry.inverse_command is None:
            raise ValueError("当前操作没有可执行的逆命令")

        result = apply_command(entry.inverse_command, project)
        undone_entry = entry.model_copy(update={"status": HistoryStatus.UNDONE})
        self._redo_stack.append(undone_entry)
        return HistoryOperationResult(
            project=result.project,
            patches=result.patches,
            history_entry=undone_entry,
        )

    def redo(
        self,
        project: Project,
        apply_command: Callable[[CanvasCommand, Project], Any],
    ) -> HistoryOperationResult:
        if not self._redo_stack:
            raise ValueError("没有可以重做的操作")

        entry = self._redo_stack.pop()
        result = apply_command(entry.command, project)
        applied_entry = entry.model_copy(update={"status": HistoryStatus.APPLIED})
        self._undo_stack.append(applied_entry)
        return HistoryOperationResult(
            project=result.project,
            patches=result.patches,
            history_entry=applied_entry,
        )

    def state(self) -> UndoRedoState:
        next_undo = self._undo_stack[-1].summary if self._undo_stack else None
        next_redo = self._redo_stack[-1].summary if self._redo_stack else None
        return UndoRedoState(
            canUndo=bool(self._undo_stack),
            canRedo=bool(self._redo_stack),
            nextUndoSummary=next_undo,
            nextRedoSummary=next_redo,
        )

    def entries(self) -> list[HistoryEntry]:
        return [entry.model_copy(deep=True) for entry in self._undo_stack]

    def snapshot(self) -> dict[str, Any]:
        """保存两条历史栈，重启后继续复用同一套命令。"""
        return {
            "undo": [entry.model_dump(by_alias=True) for entry in self._undo_stack],
            "redo": [entry.model_dump(by_alias=True) for entry in self._redo_stack],
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        self._undo_stack = [HistoryEntry.model_validate(item) for item in snapshot.get("undo", [])]
        self._redo_stack = [HistoryEntry.model_validate(item) for item in snapshot.get("redo", [])]
