from datetime import UTC, datetime
from uuid import uuid4

from voicecanvas.application.user_memory_repository import UserMemoryRepository
from voicecanvas.domain.user_memory import (
    UserMemory,
    UserMemoryContext,
    UserMemoryEvidence,
    UserMemoryKind,
    UserMemoryScope,
    UserMemoryStatus,
)


class UserMemoryService:
    """管理长期记忆的创建、确认、拒绝、删除和相关性检索。"""

    def __init__(self, repository: UserMemoryRepository) -> None:
        self._repository = repository

    def create_memory(
        self,
        *,
        user_id: str,
        kind: UserMemoryKind,
        content: str,
        scope: UserMemoryScope = "global",
        confidence: float,
        status: UserMemoryStatus = "candidate",
        evidence: list[UserMemoryEvidence] | None = None,
    ) -> UserMemory:
        now = self._now()
        memory = UserMemory(
            id=f"mem_{uuid4().hex[:12]}",
            userId=user_id,
            kind=kind,
            content=content.strip(),
            scope=scope,
            confidence=confidence,
            status=status,
            evidence=evidence or [],
            createdAt=now,
            updatedAt=now,
        )
        self._repository.save(memory)
        return memory.model_copy(deep=True)

    def save_candidate(self, memory: UserMemory) -> UserMemory:
        """保存提取器生成的候选记忆或高置信记忆。"""

        self._repository.save(memory)
        return memory.model_copy(deep=True)

    def confirm(self, memory_id: str) -> UserMemory:
        return self._update_status(memory_id, "active")

    def reject(self, memory_id: str) -> UserMemory:
        return self._update_status(memory_id, "rejected")

    def archive(self, memory_id: str) -> UserMemory:
        return self._update_status(memory_id, "archived")

    def delete(self, memory_id: str) -> None:
        self._repository.delete(memory_id)

    def list_memories(self, user_id: str, *, include_inactive: bool = False) -> list[UserMemory]:
        memories = self._repository.list_by_user(user_id)
        if include_inactive:
            return memories
        return [memory for memory in memories if memory.status == "active"]

    def context_for(
        self,
        *,
        user_id: str,
        query: str,
        scope: UserMemoryScope | None = None,
        limit: int = 8,
    ) -> UserMemoryContext:
        """检索本轮输入相关的 active 记忆，只把少量结果注入 Planner。"""

        query_tokens = self._tokens(query)
        ranked: list[tuple[float, UserMemory]] = []
        for memory in self._repository.list_by_user(user_id):
            if memory.status != "active":
                continue
            if scope is not None and memory.scope not in {"global", scope}:
                continue

            memory_tokens = self._tokens(memory.content)
            overlap = len(query_tokens & memory_tokens)
            direct_hit = any(token in memory.content for token in query_tokens)
            if overlap == 0 and not direct_hit and memory.scope != "global":
                continue

            score = memory.confidence + overlap * 0.08
            if memory.scope == scope:
                score += 0.15
            if direct_hit:
                score += 0.1
            ranked.append((score, memory))

        ranked.sort(key=lambda item: item[0], reverse=True)
        relevant = [memory.model_copy(deep=True) for _, memory in ranked[:limit]]
        now = self._now()
        for memory in relevant:
            self._repository.save(memory.model_copy(update={"last_used_at": now}))
        return UserMemoryContext(relevant=relevant)

    def _update_status(self, memory_id: str, status: UserMemoryStatus) -> UserMemory:
        memory = self._repository.get(memory_id)
        if memory is None:
            raise ValueError("长期记忆不存在")
        updated = memory.model_copy(update={"status": status, "updated_at": self._now()})
        self._repository.save(updated)
        return updated.model_copy(deep=True)

    def _tokens(self, text: str) -> set[str]:
        normalized = (
            text.strip()
            .lower()
            .replace("，", "")
            .replace("。", "")
            .replace("、", "")
            .replace("：", "")
            .replace(":", "")
            .replace(" ", "")
        )
        if not normalized:
            return set()
        tokens = {normalized[index : index + 2] for index in range(max(len(normalized) - 1, 1))}
        tokens.add(normalized)
        return tokens

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
