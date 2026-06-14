import pytest
from pydantic import ValidationError

from voicecanvas.domain.project import CanvasElement, ElementType, Project, Scene


def test_project_requires_active_scene_to_exist() -> None:
    project = Project(
        id="project_demo",
        title="Demo",
        mode="storyboard",
        scenes=[Scene(id="scene_1", name="主图", order=1)],
        activeSceneId="scene_1",
    )

    assert project.active_scene_id == "scene_1"


def test_project_rejects_invalid_active_scene() -> None:
    with pytest.raises(ValidationError, match="activeSceneId"):
        Project(
            id="project_demo",
            title="Demo",
            mode="storyboard",
            scenes=[Scene(id="scene_1", name="主图", order=1)],
            activeSceneId="scene_missing",
        )


def test_project_rejects_duplicate_scene_name() -> None:
    with pytest.raises(ValidationError, match="Scene name 不能重复"):
        Project(
            id="project_demo",
            title="Demo",
            mode="storyboard",
            scenes=[
                Scene(id="scene_1", name="镜头", order=1),
                Scene(id="scene_2", name="镜头", order=2),
            ],
            activeSceneId="scene_1",
        )


def test_canvas_element_uses_frontend_aliases() -> None:
    element = CanvasElement(
        id="el_title",
        type=ElementType.TEXT,
        x=10,
        y=20,
        width=300,
        height=60,
        zIndex=2,
        text="新品上市",
    )

    assert element.z_index == 2
    assert element.transform.x == 10
    assert element.content == {"text": "新品上市"}
    assert element.model_dump(by_alias=True)["zIndex"] == 2


def test_canvas_element_keeps_optional_description() -> None:
    element = CanvasElement(
        id="el_product",
        type=ElementType.GENERATED_ASSET,
        name="奶茶",
        description="草莓味，珍珠加量",
        x=10,
        y=20,
        width=160,
        height=180,
        zIndex=2,
        content={"alt": "奶茶"},
        asset={"kind": "product", "status": "pending", "prompt": "一杯草莓味珍珠奶茶"},
        placeholderStyle={"fill": "#ffffff"},
    )

    assert element.description == "草莓味，珍珠加量"
    assert element.model_dump(by_alias=True)["description"] == "草莓味，珍珠加量"


def test_text_element_requires_content_text() -> None:
    with pytest.raises(ValidationError, match="content.text"):
        CanvasElement(
            id="el_title",
            type=ElementType.TEXT,
            x=10,
            y=20,
            width=300,
            height=60,
            zIndex=2,
        )


def test_shape_element_requires_shape_kind() -> None:
    with pytest.raises(ValidationError, match="shape.kind"):
        CanvasElement(
            id="el_shape",
            type=ElementType.SHAPE,
            transform={"x": 10, "y": 20, "width": 160, "height": 90},
            layer={"zIndex": 1},
        )


def test_connector_requires_endpoints_and_scene_references() -> None:
    source = CanvasElement(
        id="el_source",
        type=ElementType.TEXT,
        x=10,
        y=20,
        width=160,
        height=48,
        zIndex=1,
        text="源",
    )
    target = CanvasElement(
        id="el_target",
        type=ElementType.TEXT,
        x=300,
        y=20,
        width=160,
        height=48,
        zIndex=1,
        text="目标",
    )
    connector = CanvasElement(
        id="el_connector",
        type=ElementType.CONNECTOR,
        x=0,
        y=0,
        width=1,
        height=1,
        zIndex=3,
        connector={
            "kind": "line",
            "from": {"target": {"type": "element", "elementId": "el_source"}, "anchor": "right"},
            "to": {"target": {"type": "element", "elementId": "el_target"}, "anchor": "left"},
        },
        style={"stroke": {"color": "#f15b4a", "width": 4}},
    )

    scene = Scene(
        id="scene_1",
        name="主图",
        order=1,
        elements=[source, target, connector],
    )

    assert scene.elements[-1].from_anchor.referenced_element_id == "el_source"


def test_connector_rejects_missing_scene_reference() -> None:
    with pytest.raises(ValidationError, match="connector 引用不存在的元素"):
        Scene(
            id="scene_1",
            name="主图",
            order=1,
            elements=[
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
                            "target": {"type": "element", "elementId": "el_missing"},
                            "anchor": "right",
                        },
                        "to": {"target": {"type": "point", "point": {"x": 100, "y": 100}}},
                    },
                    style={"stroke": {"color": "#f15b4a", "width": 4}},
                )
            ],
        )


def test_generated_asset_ready_requires_resource() -> None:
    with pytest.raises(ValidationError, match="assetId 或 url"):
        CanvasElement(
            id="el_asset",
            type=ElementType.GENERATED_ASSET,
            x=10,
            y=20,
            width=160,
            height=160,
            zIndex=2,
            asset={"kind": "character", "status": "ready", "prompt": "顾客"},
        )


def test_group_rejects_cycle() -> None:
    with pytest.raises(ValidationError, match="循环引用"):
        Scene(
            id="scene_1",
            name="主图",
            order=1,
            elements=[
                CanvasElement(
                    id="el_group_a",
                    type=ElementType.GROUP,
                    x=0,
                    y=0,
                    width=100,
                    height=100,
                    zIndex=1,
                    children=["el_group_b"],
                ),
                CanvasElement(
                    id="el_group_b",
                    type=ElementType.GROUP,
                    x=0,
                    y=0,
                    width=100,
                    height=100,
                    zIndex=1,
                    children=["el_group_a"],
                ),
            ],
        )

