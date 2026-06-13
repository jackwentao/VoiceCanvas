from pathlib import Path

from voicecanvas.application.user_memory_service import UserMemoryService
from voicecanvas.domain.user_memory import UserMemoryEvidence
from voicecanvas.infrastructure.local_user_memory_repository import LocalUserMemoryRepository


def test_local_repository_persists_user_memory(tmp_path: Path) -> None:
    path = tmp_path / "user-memory.json"
    service = UserMemoryService(LocalUserMemoryRepository(path))
    evidence = UserMemoryEvidence(
        source="explicit_user_statement",
        projectId="project_1",
        userInput="以后带货图默认清爽绿色",
        createdAt="2026-06-13T00:00:00+00:00",
    )

    memory = service.create_memory(
        user_id="user_1",
        kind="style_preference",
        content="用户偏好清爽绿色风格",
        scope="commerce",
        confidence=0.9,
        status="active",
        evidence=[evidence],
    )

    reloaded = LocalUserMemoryRepository(path).get(memory.id)

    assert reloaded is not None
    assert reloaded.content == "用户偏好清爽绿色风格"
    assert reloaded.evidence[0].user_input == "以后带货图默认清爽绿色"


def test_local_repository_rejects_invalid_json_shape(tmp_path: Path) -> None:
    path = tmp_path / "user-memory.json"
    path.write_text('{"invalid": true}', encoding="utf-8")
    repository = LocalUserMemoryRepository(path)

    try:
        repository.list_by_user("user_1")
    except ValueError as error:
        assert "JSON 数组" in str(error)
    else:
        raise AssertionError("长期记忆文件结构错误时应该报错")
