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
    assert element.model_dump(by_alias=True)["zIndex"] == 2

