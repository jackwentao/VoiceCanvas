import re
from datetime import UTC, datetime
from uuid import uuid4

from voicecanvas.application.command_planner import CommandPlan
from voicecanvas.domain.commands import CanvasCommand, CommandType
from voicecanvas.domain.project import Project, Scene


class DeterministicCommandRouter:
    """识别不需要 LLM 的纯确定性指令。

    只在用户输入完全表达撤销、重做或切换镜头时短路；如果同一句包含新增、
    删除、修改等额外操作意图，则返回 None，让上层继续交给 Planner/LLM。
    """

    _PUNCTUATION_PATTERN = re.compile(r"[\s，。！？、,.!?：:；;“”\"'（）()【】\[\]]+")

    _UNDO_PATTERN = re.compile(
        r"^(?:请|帮我|麻烦)?(?:撤销|回退|退回)(?:上一步|刚才|刚刚|一次|一步|刚才那一步|刚才那个操作)?(?:操作)?$"
    )
    _REDO_PATTERN = re.compile(
        r"^(?:请|帮我|麻烦)?(?:重做|恢复刚才|恢复上一步|取消撤销)"
        r"(?:上一步|刚才|刚刚|刚才那一步|一次|那一步|那个操作)?(?:操作)?$"
    )
    _SWITCH_SCENE_PATTERN = re.compile(
        r"^(?:请|帮我|麻烦)?(?:切换到|切到|跳到|打开|查看|看一下|去到)?"
        r"(?:第)?(?P<order>一|二|三|四|五|六|七|八|九|十|[1-9]\d*)"
        r"(?:个)?(?:镜头|分镜|画布|场景)$"
    )

    _SCENE_ORDERS = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }

    def route(self, user_input: str, project: Project) -> CommandPlan | None:
        normalized = self._normalize(user_input)
        if not normalized:
            return None

        if self._REDO_PATTERN.fullmatch(normalized):
            return CommandPlan("redo", [], "准备重做上一步操作")

        if self._UNDO_PATTERN.fullmatch(normalized):
            return CommandPlan("undo", [], "准备撤销上一步操作")

        match = self._SWITCH_SCENE_PATTERN.fullmatch(normalized)
        if match:
            scene_order = self._parse_order(match.group("order"))
            scene = self._scene_by_visible_order(project, scene_order)
            if scene is None:
                return CommandPlan("respond", [], f"当前项目还没有第 {scene_order} 镜头")
            return CommandPlan(
                "commands",
                [
                    CanvasCommand(
                        id=f"cmd_{uuid4().hex[:12]}",
                        type=CommandType.SWITCH_SCENE,
                        source="user_ui",
                        payload={"sceneId": scene.id},
                        reason=f"确定性切换到第 {scene_order} 镜头",
                        createdAt=self._now(),
                    )
                ],
                f"切换到第 {scene_order} 镜头",
            )

        return None

    def _normalize(self, value: str) -> str:
        return self._PUNCTUATION_PATTERN.sub("", value.strip()).lower()

    def _parse_order(self, value: str) -> int:
        if value.isdigit():
            return int(value)
        return self._SCENE_ORDERS[value]

    def _scene_by_visible_order(self, project: Project, order: int) -> Scene | None:
        ordered_scenes = sorted(project.scenes, key=lambda scene: scene.order)
        index = order - 1
        if index < 0 or index >= len(ordered_scenes):
            return None
        return ordered_scenes[index]

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
