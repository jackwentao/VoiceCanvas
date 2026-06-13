import json

from voicecanvas.adapters.llm.fake import FakeLLMClient
from voicecanvas.application.llm_command_planner import LLMCommandPlanner
from voicecanvas.application.orchestration_service import OrchestrationService
from voicecanvas.domain.patches import PatchType


def test_service_creates_storyboard_with_real_execution_pipeline() -> None:
    service = OrchestrationService()

    response = service.handle_user_input("project_demo", "创建一个三镜头的珍珠奶茶带货分镜")

    assert response.status == "COMPLETED"
    assert len(response.project.scenes) == 3
    assert response.patches
    assert response.history
    assert any(event["type"] == "CANVAS_PATCH_APPLIED" for event in response.events)


def test_service_switches_to_second_scene_after_create() -> None:
    service = OrchestrationService()
    service.handle_user_input("project_demo", "创建一个三镜头的珍珠奶茶带货分镜")

    response = service.handle_user_input("project_demo", "切换到第二镜头")

    assert response.project.active_scene_id == "scene_demo_2"
    assert response.patches[-1].type == PatchType.ACTIVE_SCENE_CHANGED


def test_service_requests_clarification_for_ambiguous_title_move() -> None:
    service = OrchestrationService()
    service.handle_user_input("project_demo", "创建一个三镜头的珍珠奶茶带货分镜")

    response = service.handle_user_input("project_demo", "把标题放上面")

    assert response.status == "WAITING_FOR_USER"
    assert response.next_action is not None
    assert response.next_action["options"]
    assert any(event["type"] == "CLARIFICATION_REQUESTED" for event in response.events)


def test_service_updates_title_and_records_inverse_history() -> None:
    service = OrchestrationService()
    service.handle_user_input("project_demo", "创建一个三镜头的珍珠奶茶带货分镜")

    response = service.handle_user_input("project_demo", "把标题改成低糖也好喝")

    title = next(
        element for element in response.project.scenes[0].elements if element.name == "标题"
    )
    assert title.text == "低糖也好喝"
    assert response.history[-1].inverse_command is not None


def test_service_clears_page_when_deleting_only_scene() -> None:
    service = OrchestrationService()
    service.handle_user_input("project_demo", "加标题，写新品上市")

    response = service.handle_user_input("project_demo", "删除最后一个镜头")

    assert len(response.project.scenes) == 1
    assert response.project.active_scene_id == "scene_1"
    assert response.project.scenes[0].elements == []
    assert response.patches[0].type == PatchType.SCENE_CLEARED


def test_service_undo_and_redo_change_project_state() -> None:
    service = OrchestrationService()
    service.handle_user_input("project_demo", "加标题，写新品上市")
    changed = service.handle_user_input("project_demo", "把标题改成低糖也好喝")

    undo = service.handle_user_input("project_demo", "撤销上一步")
    redo = service.handle_user_input("project_demo", "重做刚才那一步")

    assert changed.project.scenes[0].elements[0].text == "低糖也好喝"
    assert undo.project.scenes[0].elements[0].text == "新品上市"
    assert redo.project.scenes[0].elements[0].text == "低糖也好喝"


def test_service_returns_completed_response_for_unknown_sentence() -> None:
    service = OrchestrationService()

    response = service.handle_user_input("project_demo", "这个需求暂时无法覆盖")

    assert response.status == "COMPLETED"
    assert response.summary.command_count == 0
    assert response.patches == []


def test_service_e2e_adds_boy_as_male_character_asset() -> None:
    client = FakeLLMClient(
        [
            json.dumps(
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
                },
                ensure_ascii=False,
            )
        ]
    )
    service = OrchestrationService(planner=LLMCommandPlanner(client))

    response = service.handle_user_input("project_boy", "画一个男生")
    element = response.project.scenes[0].elements[0]

    assert response.status == "COMPLETED"
    assert element.metadata["renderHint"] == "character"
    assert element.metadata["renderVariant"] == "male"
    assert element.subject["character"]["gender"] == "male"
