from pathlib import Path

from fastapi.testclient import TestClient

from voicecanvas.api.main import create_app
from voicecanvas.application.orchestration_service import OrchestrationService
from voicecanvas.application.user_memory_service import UserMemoryService
from voicecanvas.infrastructure.local_user_memory_repository import LocalUserMemoryRepository


def _client(tmp_path: Path) -> TestClient:
    memory_service = UserMemoryService(LocalUserMemoryRepository(tmp_path / "user-memory.json"))
    return TestClient(
        create_app(
            orchestration_service=OrchestrationService(),
            user_memory_service=memory_service,
        )
    )


def test_user_memory_api_can_create_list_update_and_delete(tmp_path: Path) -> None:
    client = _client(tmp_path)

    create_response = client.post(
        "/api/users/user_1/memories",
        json={
            "kind": "style_preference",
            "content": " 用户喜欢清爽绿色和大面积留白 ",
            "scope": "commerce",
        },
    )

    assert create_response.status_code == 200
    memory = create_response.json()["memory"]
    assert memory["id"].startswith("mem_")
    assert memory["userId"] == "user_1"
    assert memory["content"] == "用户喜欢清爽绿色和大面积留白"
    assert memory["status"] == "active"
    assert memory["confidence"] == 1.0
    assert memory["evidence"][0]["source"] == "explicit_user_statement"

    list_response = client.get("/api/users/user_1/memories")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["memories"]] == [memory["id"]]

    update_response = client.patch(
        f"/api/memories/{memory['id']}",
        json={
            "kind": "workflow_preference",
            "content": "用户做带货图默认使用主图、卖点、转化三段结构",
            "scope": "storyboard",
            "confidence": 0.86,
            "status": "archived",
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()["memory"]
    assert updated["id"] == memory["id"]
    assert updated["kind"] == "workflow_preference"
    assert updated["scope"] == "storyboard"
    assert updated["confidence"] == 0.86
    assert updated["status"] == "archived"
    assert updated["createdAt"] == memory["createdAt"]
    assert updated["evidence"] == memory["evidence"]

    active_only_response = client.get("/api/users/user_1/memories")
    assert active_only_response.json()["memories"] == []

    all_response = client.get("/api/users/user_1/memories?includeInactive=true")
    assert [item["id"] for item in all_response.json()["memories"]] == [memory["id"]]

    delete_response = client.delete(f"/api/memories/{memory['id']}")
    assert delete_response.status_code == 204
    assert client.get("/api/users/user_1/memories?includeInactive=true").json()["memories"] == []


def test_user_memory_api_validates_payload_and_missing_memory(tmp_path: Path) -> None:
    client = _client(tmp_path)

    invalid_kind = client.post(
        "/api/users/user_1/memories",
        json={
            "kind": "unknown_preference",
            "content": "用户喜欢绿色",
            "scope": "global",
        },
    )
    assert invalid_kind.status_code == 422

    blank_content = client.post(
        "/api/users/user_1/memories",
        json={
            "kind": "style_preference",
            "content": "",
            "scope": "global",
        },
    )
    assert blank_content.status_code == 422

    invalid_confidence = client.patch(
        "/api/memories/mem_missing",
        json={"confidence": 1.2},
    )
    assert invalid_confidence.status_code == 422

    missing = client.patch(
        "/api/memories/mem_missing",
        json={"content": "用户喜欢清爽布局"},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "长期记忆不存在"

    created = client.post(
        "/api/users/user_1/memories",
        json={
            "kind": "style_preference",
            "content": "用户喜欢留白",
            "scope": "global",
        },
    ).json()["memory"]
    whitespace = client.patch(f"/api/memories/{created['id']}", json={"content": "   "})
    assert whitespace.status_code == 400
    assert whitespace.json()["detail"] == "长期记忆内容不能为空"
