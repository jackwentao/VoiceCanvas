from pathlib import Path

from voicecanvas.application.user_memory_service import UserMemoryService
from voicecanvas.infrastructure.local_user_memory_repository import LocalUserMemoryRepository


def _service(tmp_path: Path) -> UserMemoryService:
    return UserMemoryService(LocalUserMemoryRepository(tmp_path / "memory.json"))


def test_service_only_injects_active_relevant_memories(tmp_path: Path) -> None:
    service = _service(tmp_path)
    active = service.create_memory(
        user_id="user_1",
        kind="style_preference",
        content="用户偏好清爽绿色、留白较多的带货视觉风格",
        scope="commerce",
        confidence=0.92,
        status="active",
    )
    service.create_memory(
        user_id="user_1",
        kind="layout_preference",
        content="用户喜欢标题放在左上角",
        scope="canvas",
        confidence=0.9,
        status="candidate",
    )

    context = service.context_for(
        user_id="user_1",
        query="生成一个绿色带货分镜",
        scope="commerce",
    )

    assert [memory.id for memory in context.relevant] == [active.id]
    assert "当前用户指令" in context.usage_policy


def test_service_can_confirm_reject_archive_and_delete(tmp_path: Path) -> None:
    service = _service(tmp_path)
    memory = service.create_memory(
        user_id="user_1",
        kind="workflow_preference",
        content="用户带货分镜默认使用主图、卖点、转化三段结构",
        scope="commerce",
        confidence=0.7,
        status="candidate",
    )

    assert service.confirm(memory.id).status == "active"
    assert service.reject(memory.id).status == "rejected"
    assert service.archive(memory.id).status == "archived"

    service.delete(memory.id)

    assert service.list_memories("user_1", include_inactive=True) == []


def test_service_keeps_current_scope_boundary(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.create_memory(
        user_id="user_1",
        kind="workflow_preference",
        content="用户做分镜时默认先主图再卖点",
        scope="storyboard",
        confidence=0.9,
        status="active",
    )
    canvas_memory = service.create_memory(
        user_id="user_1",
        kind="layout_preference",
        content="用户画布标题通常放在左上角",
        scope="canvas",
        confidence=0.9,
        status="active",
    )

    context = service.context_for(
        user_id="user_1",
        query="把标题放左上角",
        scope="canvas",
    )

    assert [memory.id for memory in context.relevant] == [canvas_memory.id]
