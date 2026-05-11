from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.database import engine
from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.VERSION}


@router.get("/ready")
async def readiness_check():
    checks = {}
    healthy = True

    # Check database connectivity
    try:
        async with engine.connect() as conn:
            result = await conn.execute("SELECT 1")
            await result.fetchone()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"unavailable: {str(e)}"
        healthy = False

    # Check Redis connectivity
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.close()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"unavailable: {str(e)}"
        healthy = False

    if healthy:
        return {"status": "ready", "checks": checks}

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "not_ready", "checks": checks},
    )


@router.get("/health/celery")
async def celery_health_check():
    try:
        from app.tasks.celery_app import celery_app
        inspector = celery_app.control.inspect()
        stats = inspector.stats()
        active = inspector.active()

        workers = list(stats.keys()) if stats else []

        return {
            "status": "healthy" if workers else "no_workers",
            "workers": workers,
            "active_tasks": {k: len(v) for k, v in (active or {}).items()},
        }
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "error": str(e)},
        )
