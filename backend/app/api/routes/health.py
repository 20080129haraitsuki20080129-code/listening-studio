from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import Container, get_container

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/providers")
async def provider_health(container: Container = Depends(get_container)) -> dict:
    results = {}
    for name in container.registry.names():
        results[name] = await container.registry.get(name).healthcheck()
    return {"status": "ok", "providers": results}
