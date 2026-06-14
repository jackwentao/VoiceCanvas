from voicecanvas.application.project_repository import InMemoryProjectRepository
from voicecanvas.infrastructure.sqlite_project_repository import SQLiteProjectRepository


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


def test_repository_create_blank_project_uses_defaults_and_generated_id() -> None:
    repository = InMemoryProjectRepository()

    project = repository.create_blank_project()

    assert project.id.startswith("project_")
    assert len(project.id) == len("project_") + 12
    assert project.title == "未命名项目"
    assert project.mode == "storyboard"
    assert project.active_scene_id == "scene_1"
    assert project.scenes[0].elements == []


def test_repository_create_blank_project_keeps_saved_copy_isolated() -> None:
    repository = InMemoryProjectRepository()
    project = repository.create_blank_project(title="新项目", project_id="project_new")
    repository.save(project)

    project.title = "被外部修改"
    loaded = repository.load("project_new")

    assert loaded is not None
    assert loaded.title == "新项目"


def test_repository_projects_do_not_pollute_each_other() -> None:
    repository = InMemoryProjectRepository()
    first = repository.get_or_create("project_first")
    second = repository.get_or_create("project_second")

    first.title = "第一个项目"
    repository.save(first)

    assert repository.load("project_first").title == "第一个项目"
    assert repository.load("project_second").title == second.title


def test_sqlite_repository_persists_project_between_instances(tmp_path) -> None:
    db_path = tmp_path / "voicecanvas.sqlite3"
    first_repository = SQLiteProjectRepository(db_path)
    project = first_repository.get_or_create("project_sqlite")
    project.title = "SQLite 持久化项目"

    first_repository.save(project)
    second_repository = SQLiteProjectRepository(db_path)
    loaded = second_repository.load("project_sqlite")

    assert loaded is not None
    assert loaded.title == "SQLite 持久化项目"
    assert loaded.active_scene_id == "scene_1"


def test_sqlite_repository_create_blank_project_keeps_saved_copy_isolated(tmp_path) -> None:
    repository = SQLiteProjectRepository(tmp_path / "voicecanvas.sqlite3")
    project = repository.create_blank_project(title="新项目", project_id="project_sqlite_new")
    repository.save(project)

    project.title = "外部修改"
    loaded = repository.load("project_sqlite_new")

    assert loaded is not None
    assert loaded.title == "新项目"


def test_sqlite_repository_lists_saved_projects(tmp_path) -> None:
    repository = SQLiteProjectRepository(tmp_path / "voicecanvas.sqlite3")
    first = repository.create_blank_project(title="第一个项目", project_id="project_first")
    second = repository.create_blank_project(title="第二个项目", project_id="project_second")

    repository.save(first)
    repository.save(second)
    projects = repository.list()

    assert {project.id for project in projects} == {"project_first", "project_second"}
