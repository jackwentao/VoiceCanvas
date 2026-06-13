import re
from datetime import UTC, datetime
from uuid import uuid4

from voicecanvas.domain.user_memory import (
    UserMemory,
    UserMemoryEvidence,
    UserMemoryKind,
    UserMemoryScope,
    UserMemoryStatus,
)


class MemoryExtractor:
    """从用户表达中提取长期记忆候选，不直接修改项目状态。"""

    _sensitive_patterns = [
        re.compile(r"\b(api[_-]?key|token|secret|password)\b", re.IGNORECASE),
        re.compile(r"(密码|密钥|令牌|手机号|身份证)"),
        re.compile(r"1[3-9]\d{9}"),
    ]

    def extract(
        self,
        *,
        user_id: str,
        user_input: str,
        project_id: str | None = None,
        assistant_message: str | None = None,
    ) -> list[UserMemory]:
        text = user_input.strip()
        if not text or self._looks_sensitive(text):
            return []

        if not self._looks_memorable(text):
            return []

        kind = self._classify_kind(text)
        scope = self._classify_scope(text)
        confidence = self._confidence(text)
        status: UserMemoryStatus = "active" if confidence >= 0.85 else "candidate"
        now = self._now()
        return [
            UserMemory(
                id=f"mem_{uuid4().hex[:12]}",
                userId=user_id,
                kind=kind,
                content=self._content_for(kind, text),
                scope=scope,
                confidence=confidence,
                status=status,
                evidence=[
                    UserMemoryEvidence(
                        source="explicit_user_statement",
                        projectId=project_id,
                        userInput=user_input,
                        assistantMessage=assistant_message,
                        createdAt=now,
                    )
                ],
                createdAt=now,
                updatedAt=now,
            )
        ]

    def _looks_sensitive(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self._sensitive_patterns)

    def _looks_memorable(self, text: str) -> bool:
        keywords = [
            "以后",
            "下次",
            "默认",
            "记住",
            "我喜欢",
            "我不喜欢",
            "不要再",
            "通常",
            "习惯",
            "都用",
            "挺好",
            "不错",
        ]
        return any(keyword in text for keyword in keywords)

    def _classify_kind(self, text: str) -> UserMemoryKind:
        if any(keyword in text for keyword in ["不喜欢", "不要再", "别再", "不用"]):
            return "negative_preference"
        if any(keyword in text for keyword in ["分镜", "三段", "主图", "卖点", "转化"]):
            return "workflow_preference"
        if any(keyword in text for keyword in ["叫", "命名", "称为", "名字"]):
            return "naming_convention"
        layout_keywords = ["左上", "右上", "左下", "右下", "居中", "布局", "位置"]
        if any(keyword in text for keyword in layout_keywords):
            return "layout_preference"
        return "style_preference"

    def _classify_scope(self, text: str) -> UserMemoryScope:
        if any(keyword in text for keyword in ["带货", "商品", "购买", "转化", "卖点"]):
            return "commerce"
        if any(keyword in text for keyword in ["分镜", "镜头", "脚本"]):
            return "storyboard"
        if any(keyword in text for keyword in ["画布", "标题", "元素", "布局"]):
            return "canvas"
        return "global"

    def _confidence(self, text: str) -> float:
        if any(keyword in text for keyword in ["以后", "下次", "默认", "记住", "通常", "习惯"]):
            return 0.9
        if any(keyword in text for keyword in ["我喜欢", "我不喜欢", "不要再", "都用"]):
            return 0.82
        return 0.65

    def _content_for(self, kind: UserMemoryKind, text: str) -> str:
        labels = {
            "style_preference": "用户风格偏好",
            "layout_preference": "用户布局偏好",
            "naming_convention": "用户命名习惯",
            "workflow_preference": "用户工作流偏好",
            "negative_preference": "用户负向偏好",
        }
        return f"{labels[kind]}：{text}"

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
