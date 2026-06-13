import json

from voicecanvas.adapters.llm.base import LLMClientError
from voicecanvas.adapters.llm.fake import FakeLLMClient
from voicecanvas.application.demo_command_planner import DemoCommandPlanner
from voicecanvas.application.llm_command_planner import LLMCommandPlanner
from voicecanvas.application.orchestration_service import OrchestrationService
from voicecanvas.application.project_repository import InMemoryProjectRepository
from voicecanvas.domain.commands import CommandType
from voicecanvas.domain.project import CanvasElement, ElementType, Project, Scene


def _project():
    return InMemoryProjectRepository().get_or_create("project_demo")


def _json_response(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _project_with_two_cups() -> Project:
    return Project(
        id="project_cups",
        title="Cups",
        mode="storyboard",
        scenes=[
            Scene(
                id="scene_1",
                name="主图",
                order=1,
                elements=[
                    CanvasElement(
                        id="el_left_cup",
                        type=ElementType.SHAPE,
                        name="左侧奶茶杯",
                        x=80,
                        y=120,
                        width=120,
                        height=160,
                        zIndex=1,
                    ),
                    CanvasElement(
                        id="el_right_cup",
                        type=ElementType.SHAPE,
                        name="右侧奶茶杯",
                        x=760,
                        y=120,
                        width=120,
                        height=160,
                        zIndex=1,
                    ),
                ],
            )
        ],
        activeSceneId="scene_1",
    )


def test_llm_planner_accepts_pydantic_validated_output() -> None:
    client = FakeLLMClient(
        [
            _json_response(
                {
                    "action": "commands",
                    "message": "添加标题",
                    "commands": [
                        {
                            "type": "ADD_ELEMENT",
                            "payload": {
                                "sceneId": "scene_1",
                                "element": {
                                    "type": "text",
                                    "name": "标题",
                                    "text": "新品上市",
                                    "x": 160,
                                    "y": 70,
                                    "width": 260,
                                    "height": 64,
                                    "zIndex": 5,
                                },
                            },
                            "reason": "根据用户输入添加标题",
                        }
                    ],
                }
            )
        ]
    )

    plan = LLMCommandPlanner(client).plan("加标题，写新品上市", _project())

    assert plan.action == "commands"
    assert plan.commands[0].type == CommandType.ADD_ELEMENT
    assert plan.commands[0].source == "ai"
    assert plan.attempts[-1].validated


def test_llm_planner_splits_scene_patch_elements_into_add_element_commands() -> None:
    client = FakeLLMClient(
        [
            _json_response(
                {
                    "action": "commands",
                    "message": "更新镜头并补充元素",
                    "commands": [
                        {
                            "type": "UPDATE_SCENE",
                            "payload": {
                                "sceneId": "scene_1",
                                "patch": {
                                    "name": "主图开场",
                                    "description": "展示新品卖点",
                                    "elements": [
                                        {
                                            "type": "text",
                                            "name": "标题",
                                            "text": "新品上市",
                                            "x": 160,
                                            "y": 70,
                                            "width": 260,
                                            "height": 64,
                                            "zIndex": 5,
                                        }
                                    ],
                                },
                            },
                            "reason": "创建首屏内容",
                        }
                    ],
                }
            )
        ]
    )

    plan = LLMCommandPlanner(client).plan("创建一个三镜头带货分镜", _project())

    assert plan.action == "commands"
    assert [command.type for command in plan.commands] == [
        CommandType.UPDATE_SCENE,
        CommandType.ADD_ELEMENT,
    ]
    assert "elements" not in plan.commands[0].payload["patch"]
    assert plan.commands[1].payload["element"]["text"] == "新品上市"


def test_llm_planner_retries_invalid_json_then_succeeds() -> None:
    client = FakeLLMClient(
        [
            "这不是 JSON",
            _json_response({"action": "respond", "message": "需要补充目标元素", "commands": []}),
        ]
    )

    plan = LLMCommandPlanner(client, max_attempts=2).plan("帮我调整一下", _project())

    assert plan.action == "respond"
    assert len(client.calls) == 2
    assert "未通过校验" in client.calls[1][-1].content
    assert plan.attempts[0].error is not None


def test_llm_planner_retries_business_invalid_commands_then_succeeds() -> None:
    client = FakeLLMClient(
        [
            _json_response(
                {
                    "action": "commands",
                    "message": "添加标题",
                    "commands": [
                        {
                            "type": "ADD_ELEMENT",
                            "payload": {
                                "sceneId": "scene_missing",
                                "element": {
                                    "type": "text",
                                    "text": "新品上市",
                                    "x": 160,
                                    "y": 70,
                                    "width": 260,
                                    "height": 64,
                                    "zIndex": 5,
                                },
                            },
                        }
                    ],
                }
            ),
            _json_response(
                {
                    "action": "commands",
                    "message": "添加标题",
                    "commands": [
                        {
                            "type": "ADD_ELEMENT",
                            "payload": {
                                "sceneId": "scene_1",
                                "element": {
                                    "type": "text",
                                    "text": "新品上市",
                                    "x": 160,
                                    "y": 70,
                                    "width": 260,
                                    "height": 64,
                                    "zIndex": 5,
                                },
                            },
                        }
                    ],
                }
            ),
        ]
    )

    plan = LLMCommandPlanner(client, max_attempts=2).plan("加标题，写新品上市", _project())

    assert plan.action == "commands"
    assert plan.commands[0].payload["sceneId"] == "scene_1"
    assert "业务校验" in client.calls[1][-1].content


def test_llm_planner_falls_back_after_quota_errors() -> None:
    client = FakeLLMClient(
        [
            LLMClientError("quota", "余额不足"),
            LLMClientError("quota", "余额不足"),
        ]
    )

    plan = LLMCommandPlanner(
        client,
        fallback_planner=DemoCommandPlanner(),
        max_attempts=2,
    ).plan("创建一个三镜头的珍珠奶茶带货分镜", _project())

    assert plan.action == "commands"
    assert plan.notice is not None
    assert "额度" in plan.notice
    assert len(plan.attempts) == 2


def test_llm_planner_asks_clarification_for_ambiguous_referent_without_calling_llm() -> None:
    client = FakeLLMClient([])

    plan = LLMCommandPlanner(client).plan("把那个杯子放大一点", _project_with_two_cups())

    assert plan.action == "ask_clarification"
    assert plan.next_action is not None
    assert plan.next_action["type"] == "ASK_CLARIFICATION"
    assert len(plan.next_action["options"]) == 2
    assert client.calls == []


def test_orchestration_service_reports_planner_warning_when_llm_falls_back() -> None:
    client = FakeLLMClient([LLMClientError("network", "连接失败")])
    planner = LLMCommandPlanner(
        client,
        fallback_planner=DemoCommandPlanner(),
        max_attempts=1,
    )
    service = OrchestrationService(planner=planner)

    response = service.handle_user_input("project_demo", "创建一个三镜头的珍珠奶茶带货分镜")

    assert response.status == "COMPLETED"
    assert any(event["type"] == "PLANNER_WARNING" for event in response.events)
    assert "已降级" in response.summary.message


def test_orchestration_service_waits_for_user_when_planner_asks_clarification() -> None:
    client = FakeLLMClient([])
    planner = LLMCommandPlanner(client)
    repository = InMemoryProjectRepository()
    repository.save(_project_with_two_cups())
    service = OrchestrationService(
        repository=repository,
        planner=planner,
    )

    response = service.handle_user_input("project_cups", "把那个杯子放大一点")

    assert response.status == "WAITING_FOR_USER"
    assert response.stage == "waiting_for_user"
    assert response.next_action is not None
    assert response.next_action["resumePolicy"]["sessionId"] == response.session_id
    assert any(event["type"] == "CLARIFICATION_REQUESTED" for event in response.events)
