from typing import Any, Literal

from pydantic import BaseModel, Field

from voicecanvas.domain.conversation import ConversationMemorySnapshot, ElementMemory
from voicecanvas.domain.project import CanvasElement, Project, Scene


class ElementBounds(BaseModel):
    x: float
    y: float
    width: float
    height: float


class ElementCandidate(BaseModel):
    """用户指代可能命中的画布元素候选。"""

    scene_id: str = Field(alias="sceneId")
    element_id: str = Field(alias="elementId")
    type: str
    name: str | None = None
    text: str | None = None
    bounds: ElementBounds
    score: float
    reason: str

    model_config = {"populate_by_name": True}


class ReferentResolution(BaseModel):
    status: Literal["matched", "ambiguous", "not_found"]
    query: str
    candidates: list[ElementCandidate] = Field(default_factory=list)
    question: str | None = None
    expanded: bool = False


class ReferentResolver:
    """根据完整 Scene 信息解析“左边那个杯子”这类用户指代。"""

    _semantic_aliases = {
        "杯": ["杯", "杯子", "奶茶", "饮品", "茶杯", "咖啡杯"],
        "标题": ["标题", "主标题", "文案", "文字"],
        "商品": ["商品", "产品", "奶茶", "饮品"],
        "按钮": ["按钮", "下单", "购买", "行动"],
        "标签": ["标签", "卖点", "优惠", "低糖"],
    }
    _expanded_aliases = {
        "杯": ["陶瓷", "容器", "器皿", "瓶", "罐", "包装", "商品", "产品", "主体"],
    }

    def resolve(
        self,
        user_input: str,
        project: Project,
        memory: ConversationMemorySnapshot | None = None,
    ) -> ReferentResolution | None:
        if not self.needs_resolution(user_input):
            return None

        scene = self._active_scene(project)
        focus_candidate = self._resolve_focus_candidate(user_input, project, memory)
        if focus_candidate is not None:
            return ReferentResolution(
                status="matched",
                query=user_input,
                candidates=[focus_candidate],
            )

        strict_candidates = self._score_scene(scene, user_input, expanded=False)
        decision = self._decide(user_input, strict_candidates, expanded=False)
        if decision.status != "not_found":
            return decision

        expanded_candidates = self._score_scene(scene, user_input, expanded=True)
        expanded_decision = self._decide(user_input, expanded_candidates, expanded=True)
        if expanded_decision.candidates:
            return expanded_decision

        fallback = self._fallback_candidates(scene, user_input)
        return ReferentResolution(
            status="not_found",
            query=user_input,
            candidates=fallback,
            question="我没有准确找到你说的对象。你可以说第几个，或描述它的颜色、位置、文字。",
            expanded=True,
        )

    def needs_resolution(self, user_input: str) -> bool:
        cues = [
            "这个",
            "那个",
            "它",
            "刚才",
            "左边",
            "右边",
            "上面",
            "下面",
            "中间",
            "左",
            "右",
            "上",
            "下",
            "杯",
            "标题",
            "商品",
            "按钮",
            "标签",
        ]
        action_cues = [
            "改",
            "删",
            "删除",
            "放大",
            "缩小",
            "移动",
            "移",
            "挪",
            "居中",
            "置顶",
            "置底",
            "换",
        ]
        return any(cue in user_input for cue in cues) and any(
            cue in user_input for cue in action_cues
        )

    def _resolve_focus_candidate(
        self,
        user_input: str,
        project: Project,
        memory: ConversationMemorySnapshot | None,
    ) -> ElementCandidate | None:
        if memory is None or not memory.focus_stack:
            return None
        if not self._should_use_recent_focus(user_input):
            return None

        for item in memory.focus_stack:
            located = self._find_element(project, item.scene_id, item.element_id)
            if located is None:
                continue
            scene, element = located
            return self._candidate_from_focus(scene, element, item)
        return None

    def _should_use_recent_focus(self, user_input: str) -> bool:
        create_cues = ["画", "添加", "新增", "加一个", "生成", "创建"]
        if any(cue in user_input for cue in create_cues):
            return False

        explicit_target_cues = [
            "左边那个",
            "右边那个",
            "上面那个",
            "下面那个",
            "中间那个",
            "标题",
            "杯",
            "商品",
            "按钮",
            "标签",
            "文字",
            "人",
            "狗",
            "猫",
            "桌",
        ]
        if any(cue in user_input for cue in explicit_target_cues):
            return False

        focus_cues = ["它", "这个", "那个", "刚才", "刚刚", "上一个"]
        relative_edit_cues = [
            "往左",
            "向左",
            "左移",
            "往右",
            "向右",
            "右移",
            "上移",
            "下移",
            "移一点",
            "挪一点",
            "放大一点",
            "缩小一点",
            "大一点",
            "小一点",
        ]
        return any(cue in user_input for cue in focus_cues) or any(
            cue in user_input for cue in relative_edit_cues
        )

    def _candidate_from_focus(
        self,
        scene: Scene,
        element: CanvasElement,
        memory: ElementMemory,
    ) -> ElementCandidate:
        return ElementCandidate(
            sceneId=scene.id,
            elementId=element.id,
            type=element.type.value,
            name=element.name or memory.name,
            text=element.text or memory.text,
            bounds=ElementBounds(
                x=element.x,
                y=element.y,
                width=element.width,
                height=element.height,
            ),
            score=0.92,
            reason="命中最近操作焦点",
        )

    def _score_scene(
        self,
        scene: Scene,
        user_input: str,
        *,
        expanded: bool,
    ) -> list[ElementCandidate]:
        candidates: list[ElementCandidate] = []
        for element in scene.elements:
            score, reasons = self._score_element(scene, element, user_input, expanded=expanded)
            if score <= 0:
                continue
            candidates.append(
                ElementCandidate(
                    sceneId=scene.id,
                    elementId=element.id,
                    type=element.type.value,
                    name=element.name,
                    text=element.text,
                    bounds=ElementBounds(
                        x=element.x,
                        y=element.y,
                        width=element.width,
                        height=element.height,
                    ),
                    score=round(score, 3),
                    reason="；".join(reasons),
                )
            )

        return sorted(candidates, key=lambda item: item.score, reverse=True)

    def _score_element(
        self,
        scene: Scene,
        element: CanvasElement,
        user_input: str,
        *,
        expanded: bool,
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []
        haystack = self._element_text(element)

        semantic_score = self._semantic_score(user_input, haystack, expanded=expanded)
        if self._has_semantic_intent(user_input) and semantic_score == 0:
            return 0.0, []

        if semantic_score:
            score += semantic_score
            reasons.append("语义描述匹配")

        direct_name_score = self._direct_name_score(user_input, element)
        if direct_name_score:
            score += direct_name_score
            reasons.append("名称或文案直接命中")

        position_score, position_reason = self._position_score(scene, element, user_input)
        if position_score:
            score += position_score
            reasons.append(position_reason)

        if "它" in user_input or "这个" in user_input or "那个" in user_input:
            score += 0.08
            reasons.append("包含指代词")

        return score, reasons

    def _has_semantic_intent(self, user_input: str) -> bool:
        for keyword, aliases in self._semantic_aliases.items():
            if keyword in user_input or any(alias in user_input for alias in aliases):
                return True
        return False

    def _semantic_score(self, user_input: str, haystack: str, *, expanded: bool) -> float:
        score = 0.0
        for keyword, aliases in self._semantic_aliases.items():
            if keyword not in user_input and not any(alias in user_input for alias in aliases):
                continue
            if any(alias in haystack for alias in aliases):
                score = max(score, 0.62)
            elif expanded and any(
                alias in haystack for alias in self._expanded_aliases.get(keyword, [])
            ):
                score = max(score, 0.46)
        return score

    def _direct_name_score(self, user_input: str, element: CanvasElement) -> float:
        values = [
            element.name,
            element.text,
            element.label,
            (element.content or {}).get("label"),
            (element.content or {}).get("alt"),
        ]
        for value in values:
            text = str(value or "").strip().lower()
            if text and len(text) >= 2 and text in user_input.lower():
                return 0.7
        return 0.0

    def _position_score(
        self,
        scene: Scene,
        element: CanvasElement,
        user_input: str,
    ) -> tuple[float, str]:
        center_x = element.x + element.width / 2
        center_y = element.y + element.height / 2
        normalized_x = center_x / scene.canvas.width
        normalized_y = center_y / scene.canvas.height

        if "左" in user_input:
            return max(0.0, 0.42 * (1 - normalized_x)), "位置在画布左侧"
        if "右" in user_input:
            return max(0.0, 0.42 * normalized_x), "位置在画布右侧"
        if "上" in user_input:
            return max(0.0, 0.38 * (1 - normalized_y)), "位置在画布上方"
        if "下" in user_input:
            return max(0.0, 0.38 * normalized_y), "位置在画布下方"
        if "中间" in user_input or "中间" in user_input:
            distance = abs(normalized_x - 0.5) + abs(normalized_y - 0.5)
            return max(0.0, 0.38 * (1 - distance)), "位置接近画布中间"
        return 0.0, ""

    def _decide(
        self,
        user_input: str,
        candidates: list[ElementCandidate],
        *,
        expanded: bool,
    ) -> ReferentResolution:
        if not candidates:
            return ReferentResolution(status="not_found", query=user_input, expanded=expanded)

        filtered = [candidate for candidate in candidates if candidate.score >= 0.35]
        if not filtered:
            return ReferentResolution(
                status="not_found",
                query=user_input,
                candidates=candidates[:4],
                expanded=expanded,
            )

        top = filtered[0]
        second = filtered[1] if len(filtered) > 1 else None
        if second is None and top.score >= 0.55:
            return ReferentResolution(
                status="matched",
                query=user_input,
                candidates=[top],
                expanded=expanded,
            )
        if top.score >= 0.68 and (second is None or top.score - second.score >= 0.18):
            return ReferentResolution(
                status="matched",
                query=user_input,
                candidates=[top],
                expanded=expanded,
            )

        return ReferentResolution(
            status="ambiguous",
            query=user_input,
            candidates=filtered[:4],
            question="我找到了几个可能的对象。你想操作哪一个？",
            expanded=expanded,
        )

    def _fallback_candidates(self, scene: Scene, user_input: str) -> list[ElementCandidate]:
        spatial_candidates = self._score_scene(scene, user_input, expanded=True)
        if spatial_candidates:
            return spatial_candidates[:4]

        return [
            ElementCandidate(
                sceneId=scene.id,
                elementId=element.id,
                type=element.type.value,
                name=element.name,
                text=element.text,
                bounds=ElementBounds(
                    x=element.x,
                    y=element.y,
                    width=element.width,
                    height=element.height,
                ),
                score=0,
                reason="兜底展示当前镜头元素",
            )
            for element in scene.elements[:4]
        ]

    def _element_text(self, element: CanvasElement) -> str:
        shape_text = (
            element.shape.get("kind")
            if isinstance(element.shape, dict)
            else element.shape
        )
        values: list[str] = [
            element.type.value,
            element.name or "",
            element.text or "",
            shape_text or "",
            element.label or "",
        ]
        values.extend(str(value) for value in element.style.values())
        return " ".join(values).lower()

    def _active_scene(self, project: Project) -> Scene:
        return next(scene for scene in project.scenes if scene.id == project.active_scene_id)

    def _find_element(
        self,
        project: Project,
        scene_id: str,
        element_id: str,
    ) -> tuple[Scene, CanvasElement] | None:
        for scene in project.scenes:
            if scene.id != scene_id:
                continue
            for element in scene.elements:
                if element.id == element_id:
                    return scene, element
        return None


def resolution_to_next_action(resolution: ReferentResolution, session_id: str) -> dict[str, Any]:
    """把候选结果转换成前端可展示、可恢复的澄清动作。"""

    return {
        "type": "ASK_CLARIFICATION",
        "question": resolution.question or "你想操作哪个画布元素？",
        "expectedAnswerType": "element_selection",
        "options": [
            {
                "id": candidate.element_id,
                "label": candidate.name or candidate.text or candidate.element_id,
                "sceneId": candidate.scene_id,
                "elementId": candidate.element_id,
                "score": candidate.score,
                "reason": candidate.reason,
                "bounds": candidate.bounds.model_dump(),
            }
            for candidate in resolution.candidates
        ],
        "resumePolicy": {
            "sessionId": session_id,
            "allowVoiceAnswer": True,
            "allowOptionSelection": True,
            "resumeWith": {
                "type": "REFERENT_CLARIFICATION_RESULT",
                "originalQuery": resolution.query,
                "candidates": [
                    candidate.model_dump(by_alias=True) for candidate in resolution.candidates
                ],
            },
        },
        "resolution": {
            "status": resolution.status,
            "expanded": resolution.expanded,
        },
    }
