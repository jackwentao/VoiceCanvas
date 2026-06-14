import re
from datetime import UTC, datetime
from uuid import uuid4

from voicecanvas.application.command_planner import CommandPlan
from voicecanvas.domain.commands import CanvasCommand, CommandType
from voicecanvas.domain.project import Project, Scene


class DeterministicCommandRouter:
    """识别不需要 LLM 的纯确定性指令。

    只在用户输入完全表达撤销、重做、切换镜头、项目改名或设置镜头旁白时短路；
    如果同一句包含新增、删除等额外操作意图，则返回 None，让上层继续交给 Planner/LLM。
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
    _MENTIONED_SCENE_PATTERN = re.compile(
        r"(?:第)?(?P<order>一|二|三|四|五|六|七|八|九|十|[1-9]\d*)"
        r"(?:个)?(?:镜头|分镜|画布|场景)"
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

        project_title = self._project_title_from_text(user_input)
        if project_title:
            return CommandPlan(
                "commands",
                [
                    CanvasCommand(
                        id=f"cmd_{uuid4().hex[:12]}",
                        type=CommandType.UPDATE_PROJECT,
                        source="user_ui",
                        payload={"patch": {"title": project_title}},
                        reason="确定性修改项目名称",
                        createdAt=self._now(),
                    )
                ],
                f"项目名称已准备修改为「{project_title}」",
            )

        narration = self._narration_from_text(user_input)
        if narration:
            scene_order = self._mentioned_scene_order(normalized)
            scene = (
                self._scene_by_visible_order(project, scene_order)
                if scene_order is not None
                else self._scene_by_id(project, project.active_scene_id)
            )
            if scene is None:
                message = (
                    f"当前项目还没有第 {scene_order} 镜头"
                    if scene_order is not None
                    else "当前没有可设置旁白的镜头"
                )
                return CommandPlan("respond", [], message)
            return CommandPlan(
                "commands",
                [
                    CanvasCommand(
                        id=f"cmd_{uuid4().hex[:12]}",
                        type=CommandType.UPDATE_SCENE,
                        source="user_ui",
                        payload={"sceneId": scene.id, "patch": {"narration": narration}},
                        reason="确定性设置镜头旁白字幕",
                        createdAt=self._now(),
                    )
                ],
                f"已准备设置「{scene.name}」旁白字幕",
            )

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

    def _mentioned_scene_order(self, normalized_text: str) -> int | None:
        match = self._MENTIONED_SCENE_PATTERN.search(normalized_text)
        if not match:
            return None
        return self._parse_order(match.group("order"))

    def _scene_by_visible_order(self, project: Project, order: int) -> Scene | None:
        ordered_scenes = sorted(project.scenes, key=lambda scene: scene.order)
        index = order - 1
        if index < 0 or index >= len(ordered_scenes):
            return None
        return ordered_scenes[index]

    def _scene_by_id(self, project: Project, scene_id: str) -> Scene | None:
        return next((scene for scene in project.scenes if scene.id == scene_id), None)

    def _project_title_from_text(self, value: str) -> str:
        markers = [
            "修改项目名称为",
            "修改项目名为",
            "设置项目名称为",
            "设置项目名为",
            "项目名称改成",
            "项目名改成",
            "项目名称设置为",
            "项目名设置为",
            "项目名称叫",
            "项目名叫",
            "项目叫",
            "项目名称为",
            "项目名为",
        ]
        return self._text_after_first_marker(value, markers)

    def _narration_from_text(self, value: str) -> str:
        markers = [
            "设置旁白字幕为",
            "设置旁白字幕",
            "旁白字幕改成",
            "旁白字幕设置为",
            "旁白字幕为",
            "设置旁白为",
            "设置旁白",
            "旁白改成",
            "旁白设置为",
            "旁白为",
            "旁白",
        ]
        return self._text_after_first_marker(value, markers)

    def _text_after_first_marker(self, value: str, markers: list[str]) -> str:
        text = value.strip()
        for marker in markers:
            if marker not in text:
                continue
            candidate = text.split(marker, 1)[1]
            return candidate.lstrip("为成叫是").strip(" ：:。，,.!?！？“”\"'")
        return ""

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
