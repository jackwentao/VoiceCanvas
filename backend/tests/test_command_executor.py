from voicecanvas.application.command_executor import CommandExecutor
from voicecanvas.domain.commands import CanvasCommand, CommandType
from voicecanvas.domain.patches import PatchType
from voicecanvas.domain.project import CanvasElement, ElementType, Project, Scene


def _project(scene_count: int = 1) -> Project:
    scenes = [
        Scene(
            id="scene_1",
            name="主图",
            order=1,
            elements=[
                CanvasElement(
                    id="el_title",
                    type=ElementType.TEXT,
                    x=10,
                    y=20,
                    width=300,
                    height=60,
                    zIndex=2,
                    text="新品上市",
                )
            ],
        )
    ]
    if scene_count > 1:
        scenes.append(Scene(id="scene_2", name="产品特写", order=2))

    return Project(
        id="project_demo",
        title="Demo",
        mode="storyboard",
        scenes=scenes,
        activeSceneId="scene_1",
    )


def _command(
    command_type: CommandType, payload: dict, command_id: str = "cmd_demo"
) -> CanvasCommand:
    return CanvasCommand(
        id=command_id,
        type=command_type,
        source="ai",
        payload=payload,
        createdAt="2026-06-12T00:00:00+00:00",
    )


def test_executor_creates_scene_and_records_patch_history() -> None:
    result = CommandExecutor().execute(
        _command(CommandType.CREATE_SCENE, {"name": "产品特写", "activate": True}, "cmd_create"),
        _project(),
    )

    assert len(result.project.scenes) == 2
    assert result.project.active_scene_id == result.project.scenes[-1].id
    assert [patch.type for patch in result.patches] == [
        PatchType.SCENE_CREATED,
        PatchType.ACTIVE_SCENE_CHANGED,
    ]
    assert result.history_entry.command.payload["scene"]["id"] == result.project.scenes[-1].id
    assert result.history_entry.inverse_command is not None
    assert result.history_entry.inverse_command.type == CommandType.DELETE_SCENE


def test_executor_adds_updates_and_deletes_element() -> None:
    executor = CommandExecutor()
    add_result = executor.execute(
        _command(
            CommandType.ADD_ELEMENT,
            {
                "sceneId": "scene_1",
                "element": {
                    "type": "text",
                    "x": 100,
                    "y": 120,
                    "width": 200,
                    "height": 40,
                    "zIndex": 3,
                    "text": "低糖也好喝",
                    "name": "标题",
                },
            },
            "cmd_add",
        ),
        _project(),
    )
    element_id = add_result.patches[0].element_id

    update_result = executor.execute(
        _command(
            CommandType.UPDATE_ELEMENT,
            {"sceneId": "scene_1", "elementId": element_id, "patch": {"text": "新品低糖"}},
            "cmd_update",
        ),
        add_result.project,
    )
    delete_result = executor.execute(
        _command(
            CommandType.DELETE_ELEMENT,
            {"sceneId": "scene_1", "elementId": element_id},
            "cmd_delete",
        ),
        update_result.project,
    )

    assert add_result.patches[0].type == PatchType.ELEMENT_ADDED
    assert update_result.patches[0].patch == {"text": "新品低糖"}
    assert delete_result.patches[0].type == PatchType.ELEMENT_DELETED
    assert all(element.id != element_id for element in delete_result.project.scenes[0].elements)


def test_executor_deletes_active_scene_and_switches_to_neighbor() -> None:
    result = CommandExecutor().execute(
        _command(CommandType.DELETE_SCENE, {"sceneId": "scene_1"}, "cmd_delete_scene"),
        _project(scene_count=2),
    )

    assert [scene.id for scene in result.project.scenes] == ["scene_2"]
    assert result.project.active_scene_id == "scene_2"
    assert [patch.type for patch in result.patches] == [
        PatchType.SCENE_DELETED,
        PatchType.ACTIVE_SCENE_CHANGED,
    ]


def test_executor_clears_page_when_deleting_last_scene() -> None:
    result = CommandExecutor().execute(
        _command(CommandType.DELETE_SCENE, {"sceneId": "scene_1"}, "cmd_clear"),
        _project(),
    )

    assert len(result.project.scenes) == 1
    assert result.project.active_scene_id == "scene_1"
    assert result.project.scenes[0].elements == []
    assert result.patches[0].type == PatchType.SCENE_CLEARED
    assert result.history_entry.inverse_command is not None
    assert result.history_entry.inverse_command.type == CommandType.UPDATE_SCENE


def test_executor_centers_element_with_arrange_layout() -> None:
    result = CommandExecutor().execute(
        _command(
            CommandType.ARRANGE_LAYOUT,
            {"sceneId": "scene_1", "strategy": "center", "elementIds": ["el_title"]},
            "cmd_center",
        ),
        _project(),
    )

    element = result.project.scenes[0].elements[0]
    assert element.x == 490
    assert element.y == 330
    assert result.patches[0].type == PatchType.ELEMENT_UPDATED
    assert result.patches[0].patch == {"x": 490.0, "y": 330.0}
