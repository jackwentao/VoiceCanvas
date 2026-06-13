from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from voicecanvas.domain.commands import CanvasCommand
from voicecanvas.domain.conversation import ConversationMemorySnapshot
from voicecanvas.domain.project import Project


@dataclass(frozen=True)
class PlannerAttempt:
    """记录一次 Planner 尝试，便于排查 LLM 输出和降级原因。"""

    attempt: int
    raw_output: str | None = None
    error: str | None = None
    validated: bool = False


@dataclass(frozen=True)
class CommandPlan:
    """自然语言规划结果，后续统一交给 Validator 和 Executor。"""

    action: Literal["commands", "undo", "redo", "respond", "ask_clarification"]
    commands: list[CanvasCommand]
    message: str
    notice: str | None = None
    next_action: dict[str, Any] | None = None
    attempts: list[PlannerAttempt] = field(default_factory=list)


@dataclass(frozen=True)
class PlanningContext:
    """Planner 可选读取的上下文；普通规则 planner 可以忽略。"""

    conversation: ConversationMemorySnapshot | None = None


class CommandPlanner(Protocol):
    """将用户输入和当前项目状态转换为结构化画布计划。"""

    def plan(
        self,
        user_input: str,
        project: Project,
        *,
        context: PlanningContext | None = None,
    ) -> CommandPlan:
        ...
