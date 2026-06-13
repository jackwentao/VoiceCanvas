from voicecanvas.application.demo_command_planner import DemoCommandPlanner
from voicecanvas.application.project_repository import InMemoryProjectRepository
from voicecanvas.domain.commands import CommandType


def _project():
    return InMemoryProjectRepository().get_or_create("project_demo")


def test_planner_creates_storyboard_commands() -> None:
    plan = DemoCommandPlanner().plan("创建一个三镜头的珍珠奶茶带货分镜", _project())

    command_types = [command.type for command in plan.commands]
    assert plan.action == "commands"
    assert CommandType.UPDATE_SCENE in command_types
    assert CommandType.ADD_ELEMENT in command_types
    assert command_types.count(CommandType.CREATE_SCENE) == 2


def test_planner_switches_to_second_scene_when_it_exists() -> None:
    project = _project()
    project.scenes.append(project.scenes[0].model_copy(update={"id": "scene_2", "order": 2}))

    plan = DemoCommandPlanner().plan("切换到第二镜头", project)

    assert plan.action == "commands"
    assert plan.commands[0].type == CommandType.SWITCH_SCENE
    assert plan.commands[0].payload["sceneId"] == "scene_2"


def test_planner_switches_by_visible_scene_index_not_backend_order() -> None:
    project = _project()
    project.scenes = [
        project.scenes[0].model_copy(update={"id": "scene_backend_2", "name": "镜头1", "order": 2}),
        project.scenes[0].model_copy(update={"id": "scene_backend_3", "name": "镜头2", "order": 3}),
        project.scenes[0].model_copy(update={"id": "scene_backend_4", "name": "镜头3", "order": 4}),
    ]
    project.active_scene_id = "scene_backend_2"

    plan = DemoCommandPlanner().plan("切换到第二镜头", project)

    assert plan.action == "commands"
    assert plan.commands[0].payload["sceneId"] == "scene_backend_3"


def test_planner_updates_title_text() -> None:
    project = _project()
    storyboard = DemoCommandPlanner().plan("创建一个三镜头的珍珠奶茶带货分镜", project)
    assert storyboard.commands

    from voicecanvas.application.command_executor import CommandExecutor

    updated = CommandExecutor().execute_batch(storyboard.commands, project).project
    plan = DemoCommandPlanner().plan("把标题改成低糖也好喝", updated)

    assert plan.action == "commands"
    assert plan.commands[0].type == CommandType.UPDATE_ELEMENT
    assert plan.commands[0].payload["patch"] == {"text": "低糖也好喝"}


def test_planner_deletes_last_scene() -> None:
    plan = DemoCommandPlanner().plan("删除最后一个镜头", _project())

    assert plan.action == "commands"
    assert plan.commands[0].type == CommandType.DELETE_SCENE


def test_planner_asks_confirmation_before_clearing_scene() -> None:
    plan = DemoCommandPlanner().plan("清空当前画布", _project())

    assert plan.action == "ask_clarification"
    assert plan.next_action is not None
    assert plan.next_action["type"] == "CONFIRM_CLEAR_SCENE"
    assert plan.next_action["resumePolicy"]["resumeWith"]["type"] == "CLEAR_SCENE_CONFIRMATION"


def test_planner_responds_for_unknown_sentence() -> None:
    plan = DemoCommandPlanner().plan("帮我做一个非常复杂的镜头运动", _project())

    assert plan.action == "respond"
    assert plan.commands == []
