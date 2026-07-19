import hmac
from typing import Any
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from services.planetary_drive.namespace_manager import NamespaceManager
from apps.synthesus.desktop.synthesusd import ControllerSettings, _runtime_authorized

def create_drive_router(settings: ControllerSettings, ns: NamespaceManager) -> APIRouter:
    """
    Creates the Loopback API router for Planetary Drive.
    Exposes GET, PUT, and DELETE operations for files.
    Enforces the same strict authentication as the existing synthesusd controller API.
    """
    router = APIRouter(prefix="/api/drive", tags=["drive"])

    @router.get("/files/{path:path}")
    async def get_file(path: str, request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
            
        res = ns.get_file(path)
        if not res:
            return JSONResponse(status_code=404, content={"error": "not_found"})
            
        manifest, data = res
        return Response(content=data, headers={
            "X-Planetary-File-ID": manifest.file_id,
            "X-Planetary-Version": str(manifest.version),
            "X-Planetary-Hash": manifest.content_hash
        })

    @router.put("/files/{path:path}")
    async def put_file(path: str, request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
            
        data = await request.body()
        node_id = "local"
        manifest = ns.put_file(path, data, node_id)
        return JSONResponse(status_code=200, content=manifest.to_dict())

    @router.delete("/files/{path:path}")
    async def delete_file(path: str, request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
            
        node_id = "local"
        manifest = ns.delete_file(path, node_id)
        if not manifest:
            return JSONResponse(status_code=404, content={"error": "not_found"})
            
        return JSONResponse(status_code=200, content=manifest.to_dict())

    return router
