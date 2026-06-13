from voicecanvas.application.command_executor import CommandExecutor
from voicecanvas.application.conversation_memory import ConversationMemoryManager
from voicecanvas.domain.commands import CanvasCommand, CommandType
from voicecanvas.domain.project import Project, Scene


def _project() -> Project:
    return Project(
        id="project_memory",
        title="Memory",
        mode="free_canvas",
        scenes=[Scene(id="scene_1", name="主画布", order=1, elements=[])],
        activeSceneId="scene_1",
    )


def _command(command_type: CommandType, payload: dict, command_id: str) -> CanvasCommand:
    return CanvasCommand(
        id=command_id,
        type=command_type,
        source="ai",
        payload=payload,
        createdAt="2026-06-13T00:00:00+00:00",
    )


def test_memory_extracts_focus_from_patch_after_execution() -> None:
    executor = CommandExecutor()
    memory = ConversationMemoryManager()
    result = executor.execute(
        _command(
            CommandType.ADD_ELEMENT,
            {
                "sceneId": "scene_1",
                "element": {
                    "type": "generated_asset",
                    "name": "狗",
                    "x": 100,
                    "y": 120,
                    "width": 180,
                    "height": 120,
                    "zIndex": 5,
                    "asset": {"kind": "character", "status": "pending", "prompt": "一只狗"},
                    "placeholderStyle": {"fill": "#ffffff"},
                },
            },
            "cmd_add_dog",
        ),
        _project(),
    )

    memory.record_patch(result.patches[0], result.project)
    snapshot = memory.snapshot(result.project)

    assert snapshot.focus_stack[0].name == "狗"
    assert snapshot.focus_stack[0].element_id == result.patches[0].element_id
    assert "狗" in snapshot.focus_stack[0].aliases


def test_memory_discards_expired_turns_but_keeps_recent_focus() -> None:
    executor = CommandExecutor()
    memory = ConversationMemoryManager(max_recent_turns=2, max_focus_items=3)
    result = executor.execute(
        _command(
            CommandType.ADD_ELEMENT,
            {
                "sceneId": "scene_1",
                "element": {
                    "type": "shape",
                    "name": "主体",
                    "shape": "rectangle",
                    "x": 10,
                    "y": 20,
                    "width": 100,
                    "height": 80,
                    "zIndex": 1,
                },
            },
            "cmd_add_subject",
        ),
        _project(),
    )
    memory.record_patch(result.patches[0], result.project)

    for index in range(4):
        memory.record_turn(
            user_input=f"第 {index} 轮",
            assistant_message="已处理",
            action="commands",
            command_count=1,
        )

    snapshot = memory.snapshot(result.project)

    assert [turn.user_input for turn in snapshot.recent_turns] == ["第 2 轮", "第 3 轮"]
    assert snapshot.focus_stack[0].name == "主体"
