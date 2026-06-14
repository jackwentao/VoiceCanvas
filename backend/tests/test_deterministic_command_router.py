from voicecanvas.application.deterministic_command_router import DeterministicCommandRouter
from voicecanvas.domain.commands import CommandType
from voicecanvas.domain.project import Project, Scene


def _project() -> Project:
    return Project(
        id="project_demo",
        title="Demo",
        mode="storyboard",
        activeSceneId="scene_1",
        scenes=[
            Scene(id="scene_1", name="主图", order=1),
            Scene(id="scene_2", name="产品特写", order=2),
        ],
    )


def test_router_updates_project_title() -> None:
    plan = DeterministicCommandRouter().route("把项目名称改成低糖奶茶带货", _project())

    assert plan is not None
    assert plan.action == "commands"
    assert plan.commands[0].type == CommandType.UPDATE_PROJECT
    assert plan.commands[0].payload == {"patch": {"title": "低糖奶茶带货"}}


def test_router_updates_active_scene_narration() -> None:
    plan = DeterministicCommandRouter().route("设置旁白快来买奶茶吧", _project())

    assert plan is not None
    assert plan.action == "commands"
    assert plan.commands[0].type == CommandType.UPDATE_SCENE
    assert plan.commands[0].payload == {
        "sceneId": "scene_1",
        "patch": {"narration": "快来买奶茶吧"},
    }


def test_router_updates_named_scene_narration() -> None:
    plan = DeterministicCommandRouter().route("第二镜头设置旁白新品低糖配方", _project())

    assert plan is not None
    assert plan.action == "commands"
    assert plan.commands[0].type == CommandType.UPDATE_SCENE
    assert plan.commands[0].payload == {
        "sceneId": "scene_2",
        "patch": {"narration": "新品低糖配方"},
    }
