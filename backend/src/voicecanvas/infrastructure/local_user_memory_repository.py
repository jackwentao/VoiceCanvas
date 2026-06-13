import json
from pathlib import Path

from voicecanvas.application.user_memory_repository import UserMemoryRepository
from voicecanvas.domain.user_memory import UserMemory


class LocalUserMemoryRepository(UserMemoryRepository):
    """使用本地 JSON 文件保存长期记忆，适合 MVP 和离线演示。"""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def list_by_user(self, user_id: str) -> list[UserMemory]:
        return [
            memory.model_copy(deep=True)
            for memory in self._load_all()
            if memory.user_id == user_id
        ]

    def get(self, memory_id: str) -> UserMemory | None:
        for memory in self._load_all():
            if memory.id == memory_id:
                return memory.model_copy(deep=True)
        return None

    def save(self, memory: UserMemory) -> None:
        memories = self._load_all()
        updated = False
        for index, existing in enumerate(memories):
            if existing.id == memory.id:
                memories[index] = memory.model_copy(deep=True)
                updated = True
                break

        if not updated:
            memories.append(memory.model_copy(deep=True))
        self._save_all(memories)

    def delete(self, memory_id: str) -> None:
        memories = [memory for memory in self._load_all() if memory.id != memory_id]
        self._save_all(memories)

    def _load_all(self) -> list[UserMemory]:
        if not self._path.exists():
            return []

        with self._path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        if not isinstance(payload, list):
            raise ValueError("长期记忆文件必须是 JSON 数组")

        return [UserMemory.model_validate(item) for item in payload]

    def _save_all(self, memories: list[UserMemory]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [memory.model_dump(by_alias=True) for memory in memories]
        with self._path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
