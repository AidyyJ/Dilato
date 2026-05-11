from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.endpoints import auth, health, listings, orders, pricing, products, sourcing, sync
from app.api.v1.endpoints.orders import webhook_router as orders_webhook_router
from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import get_current_active_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.database import engine
    from app.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


def _global_exception_handler(request: Request, exc: Exception):
    """Return a consistent structured error envelope for unhandled exceptions."""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "status_code": 500},
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="Amazon-to-eBay reselling automation platform",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_exception_handler(Exception, _global_exception_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])

    protected_dependency = [Depends(get_current_active_user)]

    app.include_router(
        products.router,
        prefix="/api/v1/products",
        tags=["products"],
        dependencies=protected_dependency,
    )
    app.include_router(
        listings.router,
        prefix="/api/v1/listings",
        tags=["listings"],
        dependencies=protected_dependency,
    )
    # Order webhook is public (eBay pushes to it)
    app.include_router(
        orders_webhook_router,
        prefix="/api/v1/orders",
        tags=["orders"],
    )

    app.include_router(
        orders.router,
        prefix="/api/v1/orders",
        tags=["orders"],
        dependencies=protected_dependency,
    )
    app.include_router(
        sourcing.router,
        prefix="/api/v1/sourcing",
        tags=["sourcing"],
        dependencies=protected_dependency,
    )
    app.include_router(
        pricing.router,
        prefix="/api/v1/pricing",
        tags=["pricing"],
        dependencies=protected_dependency,
    )
    app.include_router(
        sync.router,
        prefix="/api/v1/sync",
        tags=["sync"],
        dependencies=protected_dependency,
    )

    return app


app = create_app()
