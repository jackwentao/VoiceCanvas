import json
from datetime import UTC, datetime
from uuid import uuid4

from voicecanvas.adapters.llm.fake import FakeLLMClient
from voicecanvas.application.command_planner import CommandPlan, PlanningContext
from voicecanvas.application.llm_command_planner import LLMCommandPlanner
from voicecanvas.application.orchestration_service import OrchestrationService
from voicecanvas.domain.commands import CanvasCommand, CommandType
from voicecanvas.domain.patches import PatchType
from voicecanvas.domain.project import Project


class FocusAwarePlanner:
    def plan(
        self,
        user_input: str,
        project: Project,
        *,
        context: PlanningContext | None = None,
    ) -> CommandPlan:
        if "狗" in user_input:
            return CommandPlan(
                "commands",
                [
                    self._command(
                        CommandType.ADD_ELEMENT,
                        {
                            "sceneId": project.active_scene_id,
                            "element": {
                                "type": "generated_asset",
                                "name": "狗",
                                "x": 300,
                                "y": 260,
                                "width": 180,
                                "height": 120,
                                "zIndex": 5,
                                "asset": {
                                    "kind": "character",
                                    "status": "pending",
                                    "prompt": "一只狗",
                                },
                                "placeholderStyle": {"fill": "#ffffff"},
                            },
                        },
                    )
                ],
                "添加狗",
            )

        assert context is not None
        assert context.conversation is not None
        target = context.conversation.focus_stack[0]
        return CommandPlan(
            "commands",
            [
                self._command(
                    CommandType.UPDATE_ELEMENT,
                    {
                        "sceneId": target.scene_id,
                        "elementId": target.element_id,
                        "patch": {"x": target.bounds["x"] - 40},
                    },
                )
            ],
            "移动最近主体",
        )

    def _command(self, command_type: CommandType, payload: dict) -> CanvasCommand:
        return CanvasCommand(
            id=f"cmd_{uuid4().hex[:12]}",
            type=command_type,
            source="ai",
            payload=payload,
            createdAt=datetime.now(UTC).isoformat(),
        )


def test_service_creates_storyboard_with_real_execution_pipeline() -> None:
    service = OrchestrationService()

    response = service.handle_user_input("project_demo", "创建一个三镜头的珍珠奶茶带货分镜")

    assert response.status == "COMPLETED"
    assert len(response.project.scenes) == 3
    assert response.patches
    assert response.history
    assert any(event["type"] == "CANVAS_PATCH_APPLIED" for event in response.events)


def test_service_streams_each_patch_before_final_response() -> None:
    service = OrchestrationService()

    chunks = list(service.stream_user_input("project_demo", "创建一个三镜头的珍珠奶茶带货分镜"))

    event_chunks = [chunk for chunk in chunks if chunk.type == "EVENT"]
    result_chunk = chunks[-1]
    patch_events = [
        chunk.event
        for chunk in event_chunks
        if chunk.event is not None and chunk.event["type"] == "CANVAS_PATCH_APPLIED"
    ]
    assert event_chunks[0].event is not None
    assert event_chunks[0].event["type"] == "STAGE_CHANGED"
    assert event_chunks[0].event["stage"] == "understanding"
    assert len(patch_events) >= 3
    assert result_chunk.type == "RESULT"
    assert result_chunk.response is not None
    assert result_chunk.response.status == "COMPLETED"
    assert len(result_chunk.response.patches) == len(patch_events)
    assert result_chunk.response.events[-1]["type"] == "TURN_SUMMARY"


def test_service_stream_executes_same_batch_connector_after_new_elements() -> None:
    client = FakeLLMClient(
        [
            json.dumps(
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
                },
                ensure_ascii=False,
            )
        ]
    )
    service = OrchestrationService(planner=LLMCommandPlanner(client))

    chunks = list(
        service.stream_user_input(
            "project_stream_connector",
            "画一个小女孩旁边有一只猫，让小女孩指向猫",
        )
    )

    patch_events = [
        chunk.event
        for chunk in chunks
        if chunk.type == "EVENT"
        and chunk.event is not None
        and chunk.event["type"] == "CANVAS_PATCH_APPLIED"
    ]
    result = chunks[-1].response
    assert result is not None
    assert result.status == "COMPLETED"
    assert len(patch_events) == 3
    assert result.project.scenes[0].elements[-1].type == "connector"


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


def test_service_resumes_clarification_with_spatial_voice_answer() -> None:
    service = OrchestrationService()
    service.handle_user_input("project_demo", "创建一个三镜头的珍珠奶茶带货分镜")
    waiting = service.handle_user_input("project_demo", "把标题放上面")

    response = service.resume_user_input("project_demo", waiting.session_id, "左边那个")

    assert response.status == "COMPLETED"
    assert response.patches[-1].type == PatchType.ELEMENT_UPDATED
    first_scene_title = next(
        element for element in response.project.scenes[0].elements if element.name == "标题"
    )
    assert first_scene_title.y == 36
    assert response.next_action is None


def test_service_asks_confirmation_before_clearing_scene() -> None:
    service = OrchestrationService()
    service.handle_user_input("project_demo", "加标题，写新品上市")

    response = service.handle_user_input("project_demo", "清空当前画布")

    assert response.status == "WAITING_FOR_USER"
    assert response.next_action is not None
    assert response.next_action["type"] == "CONFIRM_CLEAR_SCENE"
    assert response.patches == []


def test_service_clears_scene_after_voice_confirmation() -> None:
    service = OrchestrationService()
    service.handle_user_input("project_demo", "加标题，写新品上市")
    waiting = service.handle_user_input("project_demo", "清空当前画布")

    response = service.resume_user_input("project_demo", waiting.session_id, "确认清空")

    assert response.status == "COMPLETED"
    assert response.patches[-1].type == PatchType.SCENE_CLEARED
    assert response.project.scenes[0].elements == []


def test_service_cancels_clear_scene_when_user_says_no() -> None:
    service = OrchestrationService()
    service.handle_user_input("project_demo", "加标题，写新品上市")
    waiting = service.handle_user_input("project_demo", "清空当前画布")

    response = service.resume_user_input("project_demo", waiting.session_id, "不清空")

    assert response.status == "COMPLETED"
    assert response.summary.message == "已取消清空画布"
    assert response.patches == []
    assert response.project.scenes[0].elements


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


def test_service_extracts_short_term_memory_after_patch_for_next_turn() -> None:
    service = OrchestrationService(planner=FocusAwarePlanner())

    created = service.handle_user_input("project_focus", "画一个狗")
    moved = service.handle_user_input("project_focus", "往左移一点")

    dog = next(element for element in moved.project.scenes[0].elements if element.name == "狗")
    assert created.status == "COMPLETED"
    assert moved.status == "COMPLETED"
    assert moved.patches[-1].type == PatchType.ELEMENT_UPDATED
    assert dog.x == 260
