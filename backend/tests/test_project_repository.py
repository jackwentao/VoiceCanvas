from voicecanvas.application.project_repository import InMemoryProjectRepository


def test_repository_get_or_create_creates_demo_project() -> None:
    repository = InMemoryProjectRepository()

    project = repository.get_or_create("project_demo")

    assert project.id == "project_demo"
    assert project.active_scene_id == "scene_1"
    assert project.scenes[0].name == "空白画布"


def test_repository_save_and_load_returns_latest_project() -> None:
    repository = InMemoryProjectRepository()
    project = repository.get_or_create("project_demo")
    project.title = "更新后的项目"

    repository.save(project)
    loaded = repository.load("project_demo")

    assert loaded is not None
    assert loaded.title == "更新后的项目"


def test_repository_projects_do_not_pollute_each_other() -> None:
    repository = InMemoryProjectRepository()
    first = repository.get_or_create("project_first")
    second = repository.get_or_create("project_second")

    first.title = "第一个项目"
    repository.save(first)

    assert repository.load("project_first").title == "第一个项目"
    assert repository.load("project_second").title == second.title
