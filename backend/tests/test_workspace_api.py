"""工作台固定接口与服务端存储边界回归。"""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from voicecanvas.api.main import create_app
from voicecanvas.application.demo_command_planner import DemoCommandPlanner
from voicecanvas.application.orchestration_service import OrchestrationService
from voicecanvas.domain.telemetry import TokenUsage
from voicecanvas.infrastructure.sqlite_project_repository import SQLiteProjectRepository


def client_for(path):
    return TestClient(create_app(OrchestrationService(repository=SQLiteProjectRepository(path))))


def test_actions_validate_and_persist_without_planner(tmp_path):
    path = tmp_path / "workspace.sqlite"
    client = client_for(path)
    project = client.post("/api/projects", json={"title": "新项目"}).json()["project"]
    pid, sid = project["id"], project["activeSceneId"]
    url = f"/api/projects/{pid}/actions"
    response = client.post(
        url, json={"action": "set_background", "sceneId": sid, "color": "#ABCDEF"}
    )
    assert response.status_code == 200
    assert response.json()["project"]["scenes"][0]["canvas"]["background"]["color"] == "#abcdef"
    assert response.json()["undoRedo"]["canUndo"] is True
    # 重新创建服务，验证项目与历史都来自 SQLite。
    restarted = client_for(path)
    undone = restarted.post(url, json={"action": "undo"})
    assert undone.status_code == 200
    assert undone.json()["project"]["scenes"][0]["canvas"]["background"]["color"] == "#ffffff"
    assert undone.json()["undoRedo"]["canRedo"] is True
    redone = client_for(path).post(url, json={"action": "redo"})
    assert redone.status_code == 200
    assert redone.json()["project"]["scenes"][0]["canvas"]["background"]["color"] == "#abcdef"
    assert any(item["id"] == pid for item in restarted.get("/api/projects").json()["projects"])


def test_invalid_actions_do_not_mutate_project(tmp_path):
    client = client_for(tmp_path / "workspace.sqlite")
    before = client.get("/api/projects/test/workspace").json()["project"]
    url = "/api/projects/test/actions"
    for payload in [
        {"action": "set_background", "sceneId": "scene_1", "color": "red"},
        {"action": "set_background", "sceneId": "scene_1", "color": "#ffffff", "patch": {}},
        {"action": "execute", "command": {"type": "CLEAR_SCENE"}},
        {"action": "rename_project", "title": ""},
    ]:
        assert client.post(url, json=payload).status_code == 422
    assert client.post(url, json={"action": "switch_scene", "sceneId": "absent"}).status_code == 400
    assert client.post(url, json={"action": "undo"}).status_code == 400
    assert client.get("/api/projects/test/workspace").json()["project"] == before


def test_pending_clarification_survives_refresh_and_restart(tmp_path):
    path = tmp_path / "workspace.sqlite"
    client = client_for(path)
    response = client.post(
        "/api/orchestrations", json={"projectId": "test", "userInput": "清空当前画布"}
    )
    assert response.json()["status"] == "WAITING_FOR_USER"
    restarted = client_for(path)
    workspace = restarted.get("/api/projects/test/workspace").json()
    assert workspace["pending"]["sessionId"] == response.json()["sessionId"]
    resumed = restarted.post(
        f"/api/orchestrations/{workspace['pending']['sessionId']}/resume",
        json={"projectId": "test", "answer": "取消"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "COMPLETED"
    assert restarted.get("/api/projects/test/workspace").json()["pending"] is None


def test_catalog_and_rename_are_server_owned(tmp_path):
    client = client_for(tmp_path / "workspace.sqlite")
    assert client.get("/api/render-catalog").json()["items"]
    response = client.post(
        "/api/projects/test/actions", json={"action": "rename_project", "title": "  新分镜  "}
    )
    assert response.status_code == 200
    assert response.json()["project"]["title"] == "新分镜"


def test_token_usage_is_stored_on_backend(tmp_path):
    class UsagePlanner(DemoCommandPlanner):
        def plan(self, text, project, **kwargs):
            plan = super().plan(text, project, **kwargs)
            return replace(
                plan, token_usage=TokenUsage(promptTokens=10, completionTokens=5, totalTokens=15)
            )

    path = tmp_path / "workspace.sqlite"
    service = OrchestrationService(repository=SQLiteProjectRepository(path), planner=UsagePlanner())
    service.handle_user_input("test", "创建三镜头奶茶带货分镜")
    client = client_for(path)
    workspace = client.get("/api/projects/test/workspace").json()
    assert workspace["usage"]["total"]["totalTokens"] == 15
    assert workspace["usage"]["lastTurn"]["promptTokens"] == 10
    reset = client.post("/api/projects/test/actions", json={"action": "reset_usage"})
    assert reset.status_code == 200
    assert reset.json()["usage"] == {}
    assert client_for(path).get("/api/projects/test/workspace").json()["usage"] == {}


@pytest.mark.parametrize("choice", ["confirm", "cancel"])
def test_clear_confirmation_accepts_backend_option_values(tmp_path, choice):
    client = client_for(tmp_path / "workspace.sqlite")
    created = client.post("/api/orchestrations", json={
        "projectId": "test", "userInput": "创建三镜头奶茶带货分镜"
    }).json()
    before = created["project"]["scenes"][0]["elements"]
    assert before
    pending = client.post("/api/orchestrations", json={
        "projectId": "test", "userInput": "清空当前画布"
    }).json()
    option = next(item for item in pending["nextAction"]["options"] if item["value"] == choice)
    response = client.post(f"/api/orchestrations/{pending['sessionId']}/resume", json={
        "projectId": "test", "answer": option["value"]
    }).json()
    assert response["status"] == "COMPLETED"
    assert response["project"]["scenes"][0]["elements"] == ([] if choice == "confirm" else before)
    assert client.get("/api/projects/test/workspace").json()["pending"] is None
