from voicecanvas.application.command_validator import CommandValidator
from voicecanvas.domain.commands import CanvasCommand, CommandType
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


def _command(command_type: CommandType, payload: dict) -> CanvasCommand:
    return CanvasCommand(
        id=f"cmd_{command_type.value.lower()}",
        type=command_type,
        source="ai",
        payload=payload,
        createdAt="2026-06-12T00:00:00+00:00",
    )


def test_validator_accepts_core_supported_commands() -> None:
    project = _project()
    commands = [
        _command(CommandType.CREATE_SCENE, {"name": "产品特写", "activate": True}),
        _command(
            CommandType.ADD_ELEMENT,
            {
                "sceneId": "scene_1",
                "element": {
                    "type": "text",
                    "x": 100,
                    "y": 100,
                    "width": 240,
                    "height": 48,
                    "zIndex": 3,
                    "text": "低糖也好喝",
                },
            },
        ),
        _command(
            CommandType.UPDATE_ELEMENT,
            {
                "sceneId": "scene_1",
                "elementId": "el_title",
                "patch": {"text": "低糖也好喝"},
            },
        ),
        _command(CommandType.DELETE_SCENE, {"sceneId": "scene_1"}),
    ]

    result = CommandValidator().validate(commands, project)

    assert result.ok
    assert result.value == commands


def test_validator_reports_missing_scene_id() -> None:
    command = _command(
        CommandType.ADD_ELEMENT,
        {
            "element": {
                "type": "text",
                "x": 100,
                "y": 100,
                "width": 240,
                "height": 48,
                "zIndex": 3,
                "text": "低糖也好喝",
            }
        },
    )

    result = CommandValidator().validate([command], _project())

    assert not result.ok
    assert result.issues[0].code == "not_found"
    assert "sceneId" in result.issues[0].path


def test_validator_rejects_duplicate_scene_name() -> None:
    result = CommandValidator().validate(
        [_command(CommandType.CREATE_SCENE, {"name": "主图"})],
        _project(),
    )

    assert not result.ok
    assert result.issues[0].code == "duplicate_scene_name"


def test_validator_reports_missing_element() -> None:
    command = _command(
        CommandType.UPDATE_ELEMENT,
        {
            "sceneId": "scene_1",
            "elementId": "el_missing",
            "patch": {"text": "低糖也好喝"},
        },
    )

    result = CommandValidator().validate([command], _project())

    assert not result.ok
    assert result.issues[0].code == "not_found"
    assert "Element" in result.issues[0].message


def test_validator_accepts_element_description_patch() -> None:
    command = _command(
        CommandType.UPDATE_ELEMENT,
        {
            "sceneId": "scene_1",
            "elementId": "el_title",
            "patch": {"description": "标题用于展示新品上市卖点"},
        },
    )

    result = CommandValidator().validate([command], _project())

    assert result.ok


def test_validator_reports_invalid_element_size() -> None:
    command = _command(
        CommandType.ADD_ELEMENT,
        {
            "sceneId": "scene_1",
            "element": {
                "type": "text",
                "x": 100,
                "y": 100,
                "width": 0,
                "height": 48,
                "zIndex": 3,
                "text": "低糖也好喝",
            },
        },
    )

    result = CommandValidator().validate([command], _project())

    assert not result.ok
    assert any(issue.code == "invalid_field" for issue in result.issues)


def test_delete_last_scene_is_valid_because_it_means_clear_page() -> None:
    command = _command(CommandType.DELETE_SCENE, {"sceneId": "scene_1"})

    result = CommandValidator().validate([command], _project())

    assert result.ok


def test_validator_accepts_export_project_command() -> None:
    command = _command(CommandType.EXPORT_PROJECT, {"format": "json", "scope": "project"})

    result = CommandValidator().validate([command], _project())

    assert result.ok


def test_validator_rejects_export_missing_scene() -> None:
    command = _command(
        CommandType.EXPORT_PROJECT,
        {"format": "png", "scope": "scene", "sceneId": "missing"},
    )

    result = CommandValidator().validate([command], _project())

    assert not result.ok
    assert result.issues[0].code == "not_found"


def test_validator_rejects_unsupported_export_format() -> None:
    command = _command(CommandType.EXPORT_PROJECT, {"format": "svg", "scope": "active_scene"})

    result = CommandValidator().validate([command], _project())

    assert not result.ok
    assert result.issues[0].code == "unsupported_format"
