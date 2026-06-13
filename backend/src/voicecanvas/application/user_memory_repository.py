from typing import Protocol

from voicecanvas.domain.user_memory import UserMemory


class UserMemoryRepository(Protocol):
    """长期记忆仓储协议，应用层不关心具体存储介质。"""

    def list_by_user(self, user_id: str) -> list[UserMemory]:
        ...

    def get(self, memory_id: str) -> UserMemory | None:
        ...

    def save(self, memory: UserMemory) -> None:
        ...

    def delete(self, memory_id: str) -> None:
        ...
