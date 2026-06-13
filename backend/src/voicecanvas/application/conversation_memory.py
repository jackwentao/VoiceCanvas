from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from voicecanvas.domain.conversation import (
    ConversationMemorySnapshot,
    ConversationTurnMemory,
    ElementMemory,
)
from voicecanvas.domain.patches import CanvasPatch, PatchType
from voicecanvas.domain.project import CanvasElement, Project


class ConversationMemoryManager:
    """维护项目内的短期对话记忆，不调用外部模型，避免增加交互延时。"""

    def __init__(self, *, max_recent_turns: int = 8, max_focus_items: int = 6) -> None:
        if max_recent_turns < 1:
            raise ValueError("max_recent_turns 必须大于 0")
        if max_focus_items < 1:
            raise ValueError("max_focus_items 必须大于 0")
        self._max_recent_turns = max_recent_turns
        self._max_focus_items = max_focus_items
        self._recent_turns: list[ConversationTurnMemory] = []
        self._focus_stack: list[ElementMemory] = []

    def snapshot(self, project: Project) -> ConversationMemorySnapshot:
        """返回仍然存在于当前项目里的短期记忆。"""

        valid_ids = self._existing_element_ids(project)
        focus_stack = [
            item.model_copy(deep=True)
            for item in self._focus_stack
            if item.element_id in valid_ids
        ]
        focused_ids = {item.element_id for item in focus_stack}
        recent_turns = [
            turn.model_copy(
                update={
                    "focused_element_ids": [
                        element_id
                        for element_id in turn.focused_element_ids
                        if element_id in focused_ids
                    ]
                },
                deep=True,
            )
            for turn in self._recent_turns
        ]
        return ConversationMemorySnapshot(
            recentTurns=recent_turns,
            focusStack=focus_stack,
        )

    def record_patch(self, patch: CanvasPatch, project: Project) -> None:
        """在 patch 已发送给前端后，从真实变更里提取近期焦点。"""

        if patch.type == PatchType.ELEMENT_ADDED and patch.scene_id and patch.element:
            self._touch_element(
                patch.scene_id,
                patch.element,
                source="element_added",
                touched_at=patch.created_at,
            )
            return

        if patch.type == PatchType.ELEMENT_UPDATED and patch.scene_id and patch.element_id:
            element = self._find_element(project, patch.scene_id, patch.element_id)
            if element is not None:
                self._touch_element(
                    patch.scene_id,
                    element,
                    source="element_updated",
                    touched_at=patch.created_at,
                )
            return

        if patch.type == PatchType.ELEMENT_DELETED and patch.element_id:
            self._remove_element(patch.element_id)
            return

        if patch.type == PatchType.SCENE_CLEARED:
            cleared_ids = patch.patch.get("clearedElementIds", [])
            if isinstance(cleared_ids, list):
                for element_id in cleared_ids:
                    self._remove_element(str(element_id))
            return

        if patch.type == PatchType.SCENE_DELETED and patch.scene:
            for element in patch.scene.elements:
                self._remove_element(element.id)

    def record_turn(
        self,
        *,
        user_input: str,
        assistant_message: str,
        action: str,
        command_count: int,
    ) -> None:
        """记录最近若干轮摘要；过期轮次直接丢弃。"""

        turn = ConversationTurnMemory(
            id=f"turn_{uuid4().hex[:12]}",
            userInput=user_input,
            assistantMessage=assistant_message,
            action=action,
            commandCount=command_count,
            focusedElementIds=[item.element_id for item in self._focus_stack[:3]],
            createdAt=self._now(),
        )
        self._recent_turns.append(turn)
        self._recent_turns = self._recent_turns[-self._max_recent_turns :]

    def _touch_element(
        self,
        scene_id: str,
        element: CanvasElement,
        *,
        source: Literal[
            "element_added",
            "element_updated",
            "element_deleted",
            "scene_created",
            "scene_cleared",
        ],
        touched_at: str,
    ) -> None:
        self._remove_element(element.id)
        memory = ElementMemory(
            sceneId=scene_id,
            elementId=element.id,
            type=element.type.value,
            name=element.name,
            text=element.text,
            aliases=self._aliases_for(element),
            bounds={
                "x": element.x,
                "y": element.y,
                "width": element.width,
                "height": element.height,
            },
            source=source,
            lastTouchedAt=touched_at,
        )
        self._focus_stack.insert(0, memory)
        self._focus_stack = self._focus_stack[: self._max_focus_items]

    def _remove_element(self, element_id: str) -> None:
        self._focus_stack = [
            item for item in self._focus_stack if item.element_id != element_id
        ]

    def _aliases_for(self, element: CanvasElement) -> list[str]:
        values: list[str] = [
            element.name or "",
            element.text or "",
            element.label or "",
        ]
        if isinstance(element.content, dict):
            values.extend(
                str(element.content.get(key) or "")
                for key in ("text", "label", "alt")
            )
        if isinstance(element.asset, dict):
            values.append(str(element.asset.get("prompt") or ""))

        aliases: list[str] = []
        for value in values:
            value = value.strip()
            if value and value not in aliases:
                aliases.append(value)
        return aliases

    def _existing_element_ids(self, project: Project) -> set[str]:
        return {element.id for scene in project.scenes for element in scene.elements}

    def _find_element(
        self, project: Project, scene_id: str, element_id: str
    ) -> CanvasElement | None:
        for scene in project.scenes:
            if scene.id != scene_id:
                continue
            return next((element for element in scene.elements if element.id == element_id), None)
        return None

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
