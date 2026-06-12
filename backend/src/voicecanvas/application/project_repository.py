from voicecanvas.domain.project import Project, Scene


class InMemoryProjectRepository:
    """Demo 阶段的内存项目仓库，后续可替换为本地文件或七牛云存储适配器。"""

    def __init__(self) -> None:
        self._projects: dict[str, Project] = {}

    def get_or_create(self, project_id: str) -> Project:
        project = self._projects.get(project_id)
        if project is None:
            project = self.create_demo_project(project_id)
            self.save(project)
        return project.model_copy(deep=True)

    def load(self, project_id: str) -> Project | None:
        project = self._projects.get(project_id)
        return project.model_copy(deep=True) if project is not None else None

    def save(self, project: Project) -> None:
        self._projects[project.id] = project.model_copy(deep=True)

    def list(self) -> list[Project]:
        return [project.model_copy(deep=True) for project in self._projects.values()]

    def create_demo_project(self, project_id: str) -> Project:
        return Project(
            id=project_id,
            title="VoiceCanvas Demo",
            mode="storyboard",
            scenes=[Scene(id="scene_1", name="空白画布", order=1)],
            activeSceneId="scene_1",
        )
