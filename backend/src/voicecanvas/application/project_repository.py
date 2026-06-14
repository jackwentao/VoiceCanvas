from typing import Literal
from uuid import uuid4

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

    def create_blank_project(
        self,
        title: str = "未命名项目",
        mode: Literal["free_canvas", "storyboard"] = "storyboard",
        project_id: str | None = None,
    ) -> Project:
        """创建一个可立即编辑的空白项目，调用方负责决定是否保存。"""

        resolved_project_id = project_id or self._next_project_id()
        return Project(
            id=resolved_project_id,
            title=title.strip() or "未命名项目",
            mode=mode,
            scenes=[Scene(id="scene_1", name="空白画布", order=1)],
            activeSceneId="scene_1",
        )

    def create_demo_project(self, project_id: str) -> Project:
        return Project(
            id=project_id,
            title="VoiceCanvas Demo",
            mode="storyboard",
            scenes=[Scene(id="scene_1", name="空白画布", order=1)],
            activeSceneId="scene_1",
        )

    def _next_project_id(self) -> str:
        while True:
            project_id = f"project_{uuid4().hex[:12]}"
            if project_id not in self._projects:
                return project_id
