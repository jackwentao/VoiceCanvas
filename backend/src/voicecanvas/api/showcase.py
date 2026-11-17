"""首页画廊的只读接口，不写入或伪造用户项目。"""

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from voicecanvas.application.showcase import ShowcaseCatalog


def showcase_router(catalog: ShowcaseCatalog | None = None) -> APIRouter:
    catalog = catalog or ShowcaseCatalog()
    router = APIRouter(prefix="/api/showcase", tags=["showcase"])

    @router.get("")
    async def list_artworks(category: str | None = None) -> dict[str, Any]:
        try:
            return catalog.list(category)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/{artwork_id}/artwork")
    async def artwork(artwork_id: str) -> Response:
        try:
            content = catalog.artwork(artwork_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return Response(
            content,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"},
        )

    return router
