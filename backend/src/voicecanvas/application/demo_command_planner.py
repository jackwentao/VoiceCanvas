from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from voicecanvas.domain.commands import CanvasCommand, CommandType
from voicecanvas.domain.project import CanvasElement, ElementType, Project, Scene


@dataclass(frozen=True)
class DemoCommandPlan:
    action: Literal["commands", "undo", "redo", "respond"]
    commands: list[CanvasCommand]
    message: str


class DemoCommandPlanner:
    """将比赛 Demo 语料映射成结构化命令；真实 LLM 后续替换这一层。"""

    def plan(self, user_input: str, project: Project) -> DemoCommandPlan:
        text = user_input.strip()

        if self._contains_any(text, ["撤销", "回退", "刚才那个不要"]):
            return DemoCommandPlan("undo", [], "准备撤销上一步操作")

        if self._contains_any(text, ["重做", "恢复刚才", "取消撤销"]):
            return DemoCommandPlan("redo", [], "准备重做上一步操作")

        if "创建" in text and "分镜" in text:
            return DemoCommandPlan(
                "commands",
                self._create_storyboard_commands(project),
                "创建三镜头带货分镜",
            )

        if self._contains_any(text, ["切换到第二", "第二镜头", "看一下第二"]):
            scene = self._scene_by_order(project, 2)
            if scene is None:
                return DemoCommandPlan("respond", [], "当前项目还没有第二镜头")
            return DemoCommandPlan(
                "commands",
                [
                    self._command(
                        CommandType.SWITCH_SCENE,
                        {"sceneId": scene.id},
                        "切换到第二镜头",
                    )
                ],
                "切换到第二镜头",
            )

        if self._contains_any(text, ["删除最后", "最后一个镜头"]):
            scene = max(project.scenes, key=lambda item: item.order)
            return DemoCommandPlan(
                "commands",
                [
                    self._command(
                        CommandType.DELETE_SCENE,
                        {"sceneId": scene.id},
                        "删除最后一个镜头",
                    )
                ],
                "删除最后一个镜头",
            )

        if "标题" in text and "改成" in text:
            title = self._find_element(
                project,
                names=["标题", "主标题"],
                types=[ElementType.TEXT],
            )
            if title is None:
                return DemoCommandPlan("respond", [], "当前项目没有可修改的标题")
            return DemoCommandPlan(
                "commands",
                [
                    self._command(
                        CommandType.UPDATE_ELEMENT,
                        {
                            "sceneId": title[0].id,
                            "elementId": title[1].id,
                            "patch": {"text": self._text_after(text, "改成")},
                        },
                        "修改标题文字",
                    )
                ],
                "修改标题文字",
            )

        if self._contains_any(text, ["加标题", "加一行标题", "添加标题"]):
            return DemoCommandPlan(
                "commands",
                [
                    self._command(
                        CommandType.ADD_ELEMENT,
                        {
                            "sceneId": project.active_scene_id,
                            "element": self._text_element(
                                "标题",
                                self._text_after(text, "写"),
                                160,
                                60,
                            ),
                        },
                        "添加标题",
                    )
                ],
                "添加标题",
            )

        if self._contains_any(text, ["加商品", "添加商品", "奶茶产品"]):
            return DemoCommandPlan(
                "commands",
                [
                    self._command(
                        CommandType.ADD_ELEMENT,
                        {
                            "sceneId": project.active_scene_id,
                            "element": self._shape_element(
                                "商品",
                                470,
                                250,
                                260,
                                220,
                                {"fill": "#f8fafc", "stroke": "#2563eb"},
                            ),
                        },
                        "添加商品",
                    )
                ],
                "添加商品",
            )

        if self._contains_any(text, ["加标签", "添加标签", "优惠标签"]):
            return DemoCommandPlan(
                "commands",
                [
                    self._command(
                        CommandType.ADD_ELEMENT,
                        {
                            "sceneId": project.active_scene_id,
                            "element": self._text_element(
                                "优惠标签",
                                self._tag_text(text),
                                820,
                                210,
                            ),
                        },
                        "添加优惠标签",
                    )
                ],
                "添加优惠标签",
            )

        if self._contains_any(text, ["加箭头", "画一个箭头", "连接线"]):
            return DemoCommandPlan(
                "commands",
                [
                    self._command(
                        CommandType.ADD_ELEMENT,
                        {
                            "sceneId": project.active_scene_id,
                            "element": {
                                "type": "connector",
                                "name": "核心卖点箭头",
                                "text": "核心卖点",
                                "x": 610,
                                "y": 250,
                                "width": 250,
                                "height": 80,
                                "zIndex": 8,
                                "style": {"stroke": "#0f766e", "strokeWidth": 3},
                            },
                        },
                        "添加箭头",
                    )
                ],
                "添加箭头",
            )

        if self._contains_any(text, ["商品放大", "把商品放大", "产品放大"]):
            product = self._find_element(
                project,
                names=["商品", "奶茶产品"],
                types=[ElementType.SHAPE],
            )
            if product is None:
                return DemoCommandPlan("respond", [], "当前项目没有可放大的商品元素")
            element = product[1]
            return DemoCommandPlan(
                "commands",
                [
                    self._command(
                        CommandType.UPDATE_ELEMENT,
                        {
                            "sceneId": product[0].id,
                            "elementId": element.id,
                            "patch": {
                                "width": round(element.width * 1.15, 2),
                                "height": round(element.height * 1.15, 2),
                            },
                        },
                        "放大商品",
                    )
                ],
                "放大商品",
            )

        if self._contains_any(text, ["删除标题", "标题删掉"]):
            title = self._find_element(
                project,
                names=["标题", "主标题"],
                types=[ElementType.TEXT],
            )
            if title is None:
                return DemoCommandPlan("respond", [], "当前项目没有可删除的标题")
            return DemoCommandPlan(
                "commands",
                [
                    self._command(
                        CommandType.DELETE_ELEMENT,
                        {"sceneId": title[0].id, "elementId": title[1].id},
                        "删除标题",
                    )
                ],
                "删除标题",
            )

        return DemoCommandPlan("respond", [], "已收到需求，当前 Demo Planner 暂未覆盖该语料")

    def _create_storyboard_commands(self, project: Project) -> list[CanvasCommand]:
        first_scene = min(project.scenes, key=lambda scene: scene.order)
        return [
            self._command(
                CommandType.UPDATE_SCENE,
                {
                    "sceneId": first_scene.id,
                    "patch": {"name": "主图开场", "description": "展示新品奶茶和低糖卖点"},
                },
                "设置第一镜头",
            ),
            self._command(
                CommandType.ADD_ELEMENT,
                {
                    "sceneId": first_scene.id,
                    "element": self._text_element("标题", "新品上市", 160, 70),
                },
                "添加第一镜头标题",
            ),
            self._command(
                CommandType.ADD_ELEMENT,
                {
                    "sceneId": first_scene.id,
                    "element": self._shape_element(
                        "商品",
                        470,
                        250,
                        260,
                        220,
                        {"fill": "#fff7ed", "stroke": "#ea580c"},
                    ),
                },
                "添加第一镜头商品",
            ),
            self._command(
                CommandType.ADD_ELEMENT,
                {
                    "sceneId": first_scene.id,
                    "element": self._text_element("低糖标签", "低糖", 800, 230),
                },
                "添加第一镜头低糖标签",
            ),
            self._command(
                CommandType.CREATE_SCENE,
                {
                    "scene": self._scene(
                        "scene_demo_2",
                        "产品特写",
                        2,
                        "突出低糖和新品上市卖点",
                        [
                            self._text_element("标题", "低糖也好喝", 170, 70),
                            self._shape_element(
                                "商品",
                                500,
                                230,
                                300,
                                240,
                                {"fill": "#ecfeff", "stroke": "#0891b2"},
                            ),
                            self._text_element("低糖标签", "核心卖点", 840, 250),
                        ],
                    ),
                    "activate": False,
                },
                "创建第二镜头",
            ),
            self._command(
                CommandType.CREATE_SCENE,
                {
                    "scene": self._scene(
                        "scene_demo_3",
                        "下单转化",
                        3,
                        "展示优惠与行动按钮",
                        [
                            self._text_element("标题", "限时优惠", 170, 70),
                            self._text_element("优惠标签", "立减 10 元", 760, 220),
                            self._text_element("按钮", "马上下单", 510, 520),
                        ],
                    ),
                    "activate": False,
                },
                "创建第三镜头",
            ),
        ]

    def _scene(
        self,
        scene_id: str,
        name: str,
        order: int,
        description: str,
        elements: list[dict],
    ) -> dict:
        return {
            "id": scene_id,
            "name": name,
            "order": order,
            "description": description,
            "canvas": {
                "width": 1280,
                "height": 720,
                "background": {"type": "solid", "color": "#ffffff"},
            },
            "elements": elements,
        }

    def _text_element(self, name: str, text: str, x: float, y: float) -> dict:
        return {
            "id": f"el_{uuid4().hex[:12]}",
            "type": "text",
            "name": name,
            "text": text or name,
            "x": x,
            "y": y,
            "width": 260,
            "height": 64,
            "zIndex": 5,
            "style": {"color": "#111827", "fontSize": 32},
        }

    def _shape_element(
        self,
        name: str,
        x: float,
        y: float,
        width: float,
        height: float,
        style: dict[str, object],
    ) -> dict:
        return {
            "id": f"el_{uuid4().hex[:12]}",
            "type": "shape",
            "name": name,
            "shape": "rectangle",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "zIndex": 3,
            "style": style,
        }

    def _find_element(
        self,
        project: Project,
        *,
        names: list[str],
        types: list[ElementType],
    ) -> tuple[Scene, CanvasElement] | None:
        for scene in self._ordered_scenes_with_active_first(project):
            for element in scene.elements:
                if element.type not in types:
                    continue
                name = element.name or ""
                if any(candidate in name for candidate in names):
                    return scene, element
        return None

    def _ordered_scenes_with_active_first(self, project: Project) -> list[Scene]:
        active = [scene for scene in project.scenes if scene.id == project.active_scene_id]
        others = sorted(
            [scene for scene in project.scenes if scene.id != project.active_scene_id],
            key=lambda scene: scene.order,
        )
        return [*active, *others]

    def _scene_by_order(self, project: Project, order: int) -> Scene | None:
        return next((scene for scene in project.scenes if scene.order == order), None)

    def _tag_text(self, text: str) -> str:
        if "立减" in text:
            return "立减十元"
        if "低糖" in text:
            return "低糖"
        return "优惠"

    def _text_after(self, text: str, marker: str) -> str:
        if marker not in text:
            return ""
        return text.split(marker, 1)[1].strip(" ：:。")

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _command(self, command_type: CommandType, payload: dict, reason: str) -> CanvasCommand:
        return CanvasCommand(
            id=f"cmd_{uuid4().hex[:12]}",
            type=command_type,
            source="ai",
            payload=payload,
            reason=reason,
            createdAt=datetime.now(UTC).isoformat(),
        )
