import json

from voicecanvas.adapters.llm.base import LLMClientError
from voicecanvas.adapters.llm.fake import FakeLLMClient
from voicecanvas.application.command_planner import PlanningContext
from voicecanvas.application.demo_command_planner import DemoCommandPlanner
from voicecanvas.application.llm_command_planner import LLMCommandPlanner
from voicecanvas.application.orchestration_service import OrchestrationService
from voicecanvas.application.project_repository import InMemoryProjectRepository
from voicecanvas.domain.commands import CommandType
from voicecanvas.domain.conversation import ConversationMemorySnapshot, ElementMemory
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


def test_llm_planner_normalizes_scene_id_update_with_top_level_elements() -> None:
    client = FakeLLMClient(
        [
            _json_response(
                {
                    "action": "commands",
                    "message": "更新镜头并补充素材",
                    "commands": [
                        {
                            "type": "UPDATE_SCENE",
                            "payload": {
                                "sceneId": "scene_1",
                                "name": "开场主图",
                                "description": "展示人物和奶茶",
                                "elements": [
                                    {
                                        "type": "generated_asset",
                                        "x": 0,
                                        "y": 0,
                                        "width": 1280,
                                        "height": 720,
                                        "zIndex": 0,
                                        "asset": {
                                            "kind": "background",
                                            "status": "pending",
                                            "prompt": "奶茶店背景",
                                            "placeholderStyle": {"fill": "#ffffff"},
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                }
            )
        ]
    )

    plan = LLMCommandPlanner(client).plan("创建一个三镜头的珍珠奶茶带货分镜", _project())

    assert [command.type for command in plan.commands] == [
        CommandType.UPDATE_SCENE,
        CommandType.ADD_ELEMENT,
    ]
    assert plan.commands[0].payload["patch"]["name"] == "开场主图"
    assert "placeholderStyle" in plan.commands[1].payload["element"]


def test_llm_planner_normalizes_real_world_objects_to_generated_assets() -> None:
    client = FakeLLMClient(
        [
            _json_response(
                {
                    "action": "commands",
                    "message": "添加猫",
                    "commands": [
                        {
                            "type": "ADD_ELEMENT",
                            "payload": {
                                "sceneId": "scene_1",
                                "element": {
                                    "type": "shape",
                                    "name": "猫",
                                    "shape": "rectangle",
                                    "x": 260,
                                    "y": 260,
                                    "width": 180,
                                    "height": 140,
                                    "zIndex": 5,
                                },
                            },
                        }
                    ],
                }
            )
        ]
    )

    plan = LLMCommandPlanner(client).plan("画一个猫在桌子旁边", _project())
    element = plan.commands[0].payload["element"]

    assert element["type"] == "generated_asset"
    assert element["asset"]["kind"] == "character"
    assert element["asset"]["status"] == "pending"
    assert element["metadata"]["renderHint"] == "cat"
    assert "placeholderStyle" in element


def test_llm_planner_prioritizes_girl_subject_over_table_context() -> None:
    client = FakeLLMClient(
        [
            _json_response(
                {
                    "action": "commands",
                    "message": "添加女生",
                    "commands": [
                        {
                            "type": "ADD_ELEMENT",
                            "payload": {
                                "sceneId": "scene_1",
                                "element": {
                                    "type": "generated_asset",
                                    "name": "女生",
                                    "x": 260,
                                    "y": 220,
                                    "width": 160,
                                    "height": 220,
                                    "zIndex": 5,
                                    "content": {"alt": "女生在桌子旁边"},
                                    "asset": {
                                        "kind": "product",
                                        "status": "pending",
                                        "prompt": "一个女生在桌子旁边",
                                    },
                                    "placeholderStyle": {
                                        "fill": "#ffffff",
                                        "stroke": "#1f8a5b",
                                        "strokeWidth": 2,
                                    },
                                },
                            },
                        }
                    ],
                }
            )
        ]
    )

    plan = LLMCommandPlanner(client).plan("画一个女生在桌子旁边", _project())
    element = plan.commands[0].payload["element"]

    assert element["type"] == "generated_asset"
    assert element["asset"]["kind"] == "character"
    assert element["subject"]["character"]["category"] == "女生"
    assert element["subject"]["character"]["gender"] == "female"
    assert element["metadata"]["renderHint"] == "character"
    assert element["metadata"]["renderVariant"] == "female"


def test_llm_planner_normalizes_boy_as_male_character() -> None:
    client = FakeLLMClient(
        [
            _json_response(
                {
                    "action": "commands",
                    "message": "添加男生",
                    "commands": [
                        {
                            "type": "ADD_ELEMENT",
                            "payload": {
                                "sceneId": "scene_1",
                                "element": {
                                    "type": "generated_asset",
                                    "name": "男生",
                                    "x": 260,
                                    "y": 220,
                                    "width": 160,
                                    "height": 220,
                                    "zIndex": 5,
                                    "content": {"alt": "男生"},
                                    "asset": {
                                        "kind": "character",
                                        "status": "pending",
                                        "prompt": "一个男生站在画布中间",
                                    },
                                    "placeholderStyle": {
                                        "fill": "#ffffff",
                                        "stroke": "#1f8a5b",
                                        "strokeWidth": 2,
                                    },
                                },
                            },
                        }
                    ],
                }
            )
        ]
    )

    plan = LLMCommandPlanner(client).plan("画一个男生", _project())
    element = plan.commands[0].payload["element"]

    assert element["type"] == "generated_asset"
    assert element["metadata"]["renderHint"] == "character"
    assert element["metadata"]["renderVariant"] == "male"
    assert element["subject"]["character"]["gender"] == "male"


def test_llm_planner_normalizes_same_batch_connector_references() -> None:
    client = FakeLLMClient(
        [
            _json_response(
                {
                    "action": "commands",
                    "message": "添加小女孩、猫和箭头",
                    "commands": [
                        {
                            "type": "ADD_ELEMENT",
                            "payload": {
                                "sceneId": "scene_1",
                                "element": {
                                    "type": "generated_asset",
                                    "name": "小女孩",
                                    "x": 240,
                                    "y": 260,
                                    "width": 180,
                                    "height": 240,
                                    "zIndex": 4,
                                    "asset": {
                                        "kind": "character",
                                        "status": "pending",
                                        "prompt": "一个小女孩",
                                    },
                                    "placeholderStyle": {
                                        "fill": "#ffffff",
                                        "stroke": "#1f8a5b",
                                        "strokeWidth": 2,
                                    },
                                },
                            },
                        },
                        {
                            "type": "ADD_ELEMENT",
                            "payload": {
                                "sceneId": "scene_1",
                                "element": {
                                    "type": "shape",
                                    "name": "猫",
                                    "x": 700,
                                    "y": 360,
                                    "width": 180,
                                    "height": 140,
                                    "zIndex": 5,
                                },
                            },
                        },
                        {
                            "type": "ADD_ELEMENT",
                            "payload": {
                                "sceneId": "scene_1",
                                "element": {
                                    "type": "connector",
                                    "name": "小女孩指向猫",
                                    "from": "小女孩",
                                    "to": "猫",
                                    "content": {"label": "指向猫"},
                                    "x": 0,
                                    "y": 0,
                                    "width": 1,
                                    "height": 1,
                                    "zIndex": 8,
                                },
                            },
                        },
                    ],
                }
            )
        ]
    )

    plan = LLMCommandPlanner(client).plan("画一个小女孩旁边有一只猫，让小女孩指向猫", _project())

    assert plan.action == "commands"
    assert [command.type for command in plan.commands] == [
        CommandType.ADD_ELEMENT,
        CommandType.ADD_ELEMENT,
        CommandType.ADD_ELEMENT,
    ]
    girl = plan.commands[0].payload["element"]
    cat = plan.commands[1].payload["element"]
    connector = plan.commands[2].payload["element"]
    assert girl["id"].startswith("el_ai_")
    assert cat["metadata"]["renderHint"] == "cat"
    assert connector["connector"]["from"]["target"]["elementId"] == girl["id"]
    assert connector["connector"]["to"]["target"]["elementId"] == cat["id"]
    assert plan.attempts[-1].validated


def test_llm_planner_keeps_structured_text_content_valid() -> None:
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
                                    "x": 440,
                                    "y": 50,
                                    "width": 400,
                                    "height": 80,
                                    "zIndex": 1,
                                    "content": {"text": "新品上市"},
                                },
                            },
                        }
                    ],
                }
            )
        ]
    )

    plan = LLMCommandPlanner(client).plan("加标题，写新品上市", _project())
    element = plan.commands[0].payload["element"]

    assert element["text"] == "新品上市"
    assert element["content"]["text"] == "新品上市"


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


def test_llm_planner_sends_conversation_context_and_resolved_focus() -> None:
    project = Project(
        id="project_dog",
        title="Dog",
        mode="free_canvas",
        scenes=[
            Scene(
                id="scene_1",
                name="主画布",
                order=1,
                elements=[
                    CanvasElement(
                        id="el_dog",
                        type=ElementType.GENERATED_ASSET,
                        name="狗",
                        x=240,
                        y=260,
                        width=180,
                        height=120,
                        zIndex=5,
                        asset={"kind": "character", "status": "pending", "prompt": "一只狗"},
                        placeholderStyle={"fill": "#ffffff"},
                    )
                ],
            )
        ],
        activeSceneId="scene_1",
    )
    context = PlanningContext(
        conversation=ConversationMemorySnapshot(
            focusStack=[
                ElementMemory(
                    sceneId="scene_1",
                    elementId="el_dog",
                    type="generated_asset",
                    name="狗",
                    bounds={"x": 240, "y": 260, "width": 180, "height": 120},
                    source="element_added",
                    lastTouchedAt="2026-06-13T00:00:00+00:00",
                )
            ]
        )
    )
    client = FakeLLMClient(
        [
            _json_response(
                {
                    "action": "commands",
                    "message": "移动狗",
                    "commands": [
                        {
                            "type": "UPDATE_ELEMENT",
                            "payload": {
                                "sceneId": "scene_1",
                                "elementId": "el_dog",
                                "patch": {"x": 200},
                            },
                        }
                    ],
                }
            )
        ]
    )

    plan = LLMCommandPlanner(client).plan("往左移一点", project, context=context)
    payload = json.loads(client.calls[0][-1].content)

    assert plan.action == "commands"
    assert payload["conversationContext"]["focusStack"][0]["elementId"] == "el_dog"
    assert payload["resolvedTarget"]["elementId"] == "el_dog"


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
