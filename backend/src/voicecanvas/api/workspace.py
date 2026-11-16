"""独立工作台路由；复用应用服务，与页面布局和渲染技术无关。"""

from typing import Any

from fastapi import APIRouter, HTTPException

from voicecanvas.application.orchestration_service import OrchestrationService
from voicecanvas.application.render_catalog import get_render_catalog
from voicecanvas.application.workspace_actions import WorkspaceAction


def workspace_router(service: OrchestrationService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["workspace"])

    @router.get("/projects")
    async def list_projects() -> dict[str, Any]:
        return {"projects": service.list_projects()}

    @router.get("/render-catalog")
    async def render_catalog() -> dict[str, Any]:
        return get_render_catalog().data

    @router.get("/projects/{project_id}/workspace")
    async def workspace(project_id: str) -> dict[str, Any]:
        return service.workspace_state(project_id)

    @router.post("/projects/{project_id}/actions")
    async def action(project_id: str, request: WorkspaceAction) -> dict[str, Any]:
        try:
            return service.execute_ui_action(project_id, request)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return router
