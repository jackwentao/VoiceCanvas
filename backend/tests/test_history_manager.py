from voicecanvas.application.command_executor import CommandExecutor
from voicecanvas.application.history_manager import HistoryManager
from voicecanvas.domain.commands import CanvasCommand, CommandType
from voicecanvas.domain.history import HistoryStatus
from voicecanvas.domain.project import CanvasElement, ElementType, Project, Scene


def _project() -> Project:
    return Project(
        id="project_demo",
        title="Demo",
        mode="storyboard",
        scenes=[
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
        ],
        activeSceneId="scene_1",
    )


def _project_with_two_scenes() -> Project:
    return Project(
        id="project_demo",
        title="Demo",
        mode="storyboard",
        scenes=[
            Scene(id="scene_1", name="主图", order=1),
            Scene(
                id="scene_2",
                name="产品特写",
                order=2,
                elements=[
                    CanvasElement(
                        id="el_product",
                        type=ElementType.TEXT,
                        x=10,
                        y=20,
                        width=300,
                        height=60,
                        zIndex=2,
                        text="产品特写",
                    )
                ],
            ),
        ],
        activeSceneId="scene_2",
    )


def _command(command_type: CommandType, payload: dict, command_id: str) -> CanvasCommand:
    return CanvasCommand(
        id=command_id,
        type=command_type,
        source="ai",
        payload=payload,
        createdAt="2026-06-12T00:00:00+00:00",
    )


def test_history_undo_redo_add_element() -> None:
    executor = CommandExecutor()
    history = HistoryManager()
    result = executor.execute(
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
                },
            },
            "cmd_add",
        ),
        _project(),
    )
    history.record(result.history_entry)
    added_id = result.patches[0].element_id

    undo = history.undo(result.project, executor.apply_without_recording)
    redo = history.redo(undo.project, executor.apply_without_recording)

    assert undo.history_entry.status == HistoryStatus.UNDONE
    assert all(element.id != added_id for element in undo.project.scenes[0].elements)
    assert any(element.id == added_id for element in redo.project.scenes[0].elements)
    assert history.state().can_undo


def test_history_undo_redo_update_element() -> None:
    executor = CommandExecutor()
    history = HistoryManager()
    result = executor.execute(
        _command(
            CommandType.UPDATE_ELEMENT,
            {"sceneId": "scene_1", "elementId": "el_title", "patch": {"text": "低糖也好喝"}},
            "cmd_update",
        ),
        _project(),
    )
    history.record(result.history_entry)

    undo = history.undo(result.project, executor.apply_without_recording)
    redo = history.redo(undo.project, executor.apply_without_recording)

    assert undo.project.scenes[0].elements[0].text == "新品上市"
    assert redo.project.scenes[0].elements[0].text == "低糖也好喝"


def test_history_undo_delete_element_restores_snapshot() -> None:
    executor = CommandExecutor()
    history = HistoryManager()
    result = executor.execute(
        _command(
            CommandType.DELETE_ELEMENT,
            {"sceneId": "scene_1", "elementId": "el_title"},
            "cmd_delete",
        ),
        _project(),
    )
    history.record(result.history_entry)

    undo = history.undo(result.project, executor.apply_without_recording)

    assert undo.project.scenes[0].elements[0].id == "el_title"
    assert undo.project.scenes[0].elements[0].text == "新品上市"


def test_history_undo_redo_clear_last_scene() -> None:
    executor = CommandExecutor()
    history = HistoryManager()
    result = executor.execute(
        _command(CommandType.DELETE_SCENE, {"sceneId": "scene_1"}, "cmd_clear"),
        _project(),
    )
    history.record(result.history_entry)

    undo = history.undo(result.project, executor.apply_without_recording)
    redo = history.redo(undo.project, executor.apply_without_recording)

    assert undo.project.scenes[0].elements[0].id == "el_title"
    assert redo.project.scenes[0].elements == []


def test_history_undo_redo_delete_active_scene_restores_scene_and_focus() -> None:
    executor = CommandExecutor()
    history = HistoryManager()
    result = executor.execute(
        _command(CommandType.DELETE_SCENE, {"sceneId": "scene_2"}, "cmd_delete_scene"),
        _project_with_two_scenes(),
    )
    history.record(result.history_entry)

    undo = history.undo(result.project, executor.apply_without_recording)
    redo = history.redo(undo.project, executor.apply_without_recording)

    assert [scene.id for scene in result.project.scenes] == ["scene_1"]
    assert result.project.active_scene_id == "scene_1"
    assert [scene.id for scene in undo.project.scenes] == ["scene_1", "scene_2"]
    assert undo.project.active_scene_id == "scene_2"
    assert redo.project.active_scene_id == "scene_1"


def test_history_recording_new_command_clears_redo_stack() -> None:
    executor = CommandExecutor()
    history = HistoryManager()
    first = executor.execute(
        _command(
            CommandType.UPDATE_ELEMENT,
            {"sceneId": "scene_1", "elementId": "el_title", "patch": {"text": "低糖也好喝"}},
            "cmd_update_1",
        ),
        _project(),
    )
    history.record(first.history_entry)
    undo = history.undo(first.project, executor.apply_without_recording)
    assert history.state().can_redo

    second = executor.execute(
        _command(
            CommandType.UPDATE_ELEMENT,
            {"sceneId": "scene_1", "elementId": "el_title", "patch": {"text": "新品低糖"}},
            "cmd_update_2",
        ),
        undo.project,
    )
    history.record(second.history_entry)

    assert not history.state().can_redo
