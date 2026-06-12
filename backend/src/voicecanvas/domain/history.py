from enum import StrEnum

from pydantic import BaseModel, Field

from voicecanvas.domain.commands import CanvasCommand
from voicecanvas.domain.patches import CanvasPatch


class HistoryStatus(StrEnum):
    APPLIED = "applied"
    UNDONE = "undone"
    FAILED = "failed"


class HistoryEntry(BaseModel):
    id: str
    command: CanvasCommand
    patches: list[CanvasPatch]
    summary: str
    status: HistoryStatus = HistoryStatus.APPLIED
    created_at: str = Field(alias="createdAt")
    inverse_command: CanvasCommand | None = Field(default=None, alias="inverseCommand")
    error: str | None = None

    model_config = {"populate_by_name": True}


class UndoRedoState(BaseModel):
    can_undo: bool = Field(alias="canUndo")
    can_redo: bool = Field(alias="canRedo")
    next_undo_summary: str | None = Field(default=None, alias="nextUndoSummary")
    next_redo_summary: str | None = Field(default=None, alias="nextRedoSummary")

    model_config = {"populate_by_name": True}
