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


def test_executor_adds_all_structured_element_types() -> None:
    executor = CommandExecutor()
    project = _project()

    element_drafts = [
        {
            "type": "text",
            "transform": {"x": 100, "y": 120, "width": 200, "height": 40},
            "layer": {"zIndex": 3},
            "content": {"text": "低糖也好喝"},
            "style": {"fontSize": 28, "color": "#173b2c"},
        },
        {
            "type": "shape",
            "transform": {"x": 320, "y": 120, "width": 160, "height": 90},
            "layer": {"zIndex": 4},
            "shape": {"kind": "rounded_rectangle"},
            "content": {"label": "奶茶"},
            "style": {"fill": {"type": "solid", "color": "#ffffff"}},
        },
        {
            "type": "image",
            "transform": {"x": 500, "y": 120, "width": 120, "height": 120},
            "layer": {"zIndex": 5},
            "content": {"url": "https://example.com/product.png", "alt": "产品图"},
            "image": {"fit": "cover"},
        },
        {
            "type": "generated_asset",
            "transform": {"x": 640, "y": 120, "width": 120, "height": 160},
            "layer": {"zIndex": 6},
            "content": {"alt": "顾客"},
            "asset": {"kind": "character", "status": "pending", "prompt": "顾客微笑"},
            "placeholderStyle": {"fill": "#ffffff", "stroke": "#1f8a5b", "strokeWidth": 2},
        },
        {
            "type": "connector",
            "transform": {"x": 0, "y": 0, "width": 1, "height": 1},
            "layer": {"zIndex": 7},
            "content": {"label": "核心卖点"},
            "connector": {
                "kind": "line",
                "from": {"target": {"type": "element", "elementId": "el_title"}, "anchor": "right"},
                "to": {"target": {"type": "point", "point": {"x": 420, "y": 160}}},
            },
            "style": {"stroke": {"color": "#f15b4a", "width": 4}},
        },
        {
            "type": "group",
            "transform": {"x": 90, "y": 110, "width": 420, "height": 180},
            "layer": {"zIndex": 8},
            "children": ["el_title"],
            "group": {"layout": "free"},
        },
    ]

    for index, draft in enumerate(element_drafts):
        result = executor.execute(
            _command(
                CommandType.ADD_ELEMENT,
                {"sceneId": "scene_1", "element": draft},
                f"cmd_add_{index}",
            ),
            project,
        )
        project = result.project

    types = [element.type.value for element in project.scenes[0].elements]
    assert "generated_asset" in types
    assert "group" in types
    assert "connector" in types


def test_executor_merges_structured_element_patch() -> None:
    executor = CommandExecutor()
    add_result = executor.execute(
        _command(
            CommandType.ADD_ELEMENT,
            {
                "sceneId": "scene_1",
                "element": {
                    "type": "text",
                    "transform": {"x": 100, "y": 120, "width": 200, "height": 40},
                    "layer": {"zIndex": 3},
                    "content": {"text": "低糖也好喝"},
                    "style": {"fontSize": 28, "color": "#173b2c"},
                },
            },
            "cmd_add_structured",
        ),
        _project(),
    )
    element_id = add_result.patches[0].element_id

    update_result = executor.execute(
        _command(
            CommandType.UPDATE_ELEMENT,
            {
                "sceneId": "scene_1",
                "elementId": element_id,
                "patch": {
                    "transform": {"x": 140},
                    "content": {"text": "新品低糖"},
                },
            },
            "cmd_update_structured",
        ),
        add_result.project,
    )

    element = update_result.project.scenes[0].elements[-1]
    assert element.transform.x == 140
    assert element.transform.width == 200
    assert element.content["text"] == "新品低糖"
    assert element.style["color"] == "#173b2c"


def test_executor_keeps_transform_and_legacy_size_in_sync() -> None:
    executor = CommandExecutor()
    add_result = executor.execute(
        _command(
            CommandType.ADD_ELEMENT,
            {
                "sceneId": "scene_1",
                "element": {
                    "type": "generated_asset",
                    "transform": {"x": 100, "y": 120, "width": 160, "height": 120},
                    "layer": {"zIndex": 4},
                    "content": {"alt": "猫"},
                    "asset": {"kind": "character", "status": "pending", "prompt": "猫"},
                    "placeholderStyle": {"fill": "#ffffff", "stroke": "#1f8a5b", "strokeWidth": 2},
                    "metadata": {"renderKey": "cat"},
                },
            },
            "cmd_add_cat",
        ),
        _project(),
    )
    element_id = add_result.patches[0].element_id

    legacy_update = executor.execute(
        _command(
            CommandType.UPDATE_ELEMENT,
            {
                "sceneId": "scene_1",
                "elementId": element_id,
                "patch": {"width": 240, "height": 180},
            },
            "cmd_resize_cat_legacy",
        ),
        add_result.project,
    )
    legacy_element = legacy_update.project.scenes[0].elements[-1]
    assert legacy_element.width == 240
    assert legacy_element.height == 180
    assert legacy_element.transform.width == 240
    assert legacy_element.transform.height == 180

    structured_update = executor.execute(
        _command(
            CommandType.UPDATE_ELEMENT,
            {
                "sceneId": "scene_1",
                "elementId": element_id,
                "patch": {"transform": {"width": 120, "height": 90}},
            },
            "cmd_resize_cat_structured",
        ),
        legacy_update.project,
    )
    structured_element = structured_update.project.scenes[0].elements[-1]
    assert structured_element.width == 120
    assert structured_element.height == 90
    assert structured_element.transform.width == 120
    assert structured_element.transform.height == 90


def test_executor_degrades_connector_when_target_element_is_deleted() -> None:
    project = Project(
        id="project_demo",
        title="Demo",
        mode="storyboard",
        activeSceneId="scene_1",
        scenes=[
            Scene(
                id="scene_1",
                name="主图",
                order=1,
                elements=[
                    CanvasElement(
                        id="el_source",
                        type=ElementType.TEXT,
                        x=10,
                        y=20,
                        width=160,
                        height=48,
                        zIndex=1,
                        text="源",
                    ),
                    CanvasElement(
                        id="el_target",
                        type=ElementType.TEXT,
                        x=300,
                        y=20,
                        width=160,
                        height=48,
                        zIndex=1,
                        text="目标",
                    ),
                    CanvasElement(
                        id="el_connector",
                        type=ElementType.CONNECTOR,
                        x=0,
                        y=0,
                        width=1,
                        height=1,
                        zIndex=3,
                        connector={
                            "kind": "line",
                            "from": {
                                "target": {"type": "element", "elementId": "el_source"},
                                "anchor": "right",
                            },
                            "to": {
                                "target": {"type": "element", "elementId": "el_target"},
                                "anchor": "left",
                            },
                        },
                        style={"stroke": {"color": "#f15b4a", "width": 4}},
                    ),
                ],
            )
        ],
    )

    result = CommandExecutor().execute(
        _command(
            CommandType.DELETE_ELEMENT,
            {"sceneId": "scene_1", "elementId": "el_target"},
            "cmd_delete_target",
        ),
        project,
    )

    connector = next(
        element
        for element in result.project.scenes[0].elements
        if element.id == "el_connector"
    )
    assert connector.type == ElementType.UNKNOWN
    assert connector.reason == "invalid_reference"
    assert result.history_entry.inverse_command is not None
    assert result.history_entry.inverse_command.type == CommandType.UPDATE_SCENE


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


def test_executor_clears_active_scene_with_clear_scene_command() -> None:
    result = CommandExecutor().execute(
        _command(CommandType.CLEAR_SCENE, {"sceneId": "scene_1"}, "cmd_clear_scene"),
        _project(scene_count=2),
    )

    assert len(result.project.scenes) == 2
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
