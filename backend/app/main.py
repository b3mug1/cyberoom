from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.api.role_routes import router as role_router
from app.core.config import get_settings
from app.db import engine, redis_client
from app.middleware.rate_limit import RateLimitMiddleware
from app.services.errors import ServiceError


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Cyberoom API", version="0.1.0", debug=settings.app_debug)
    app.add_middleware(RateLimitMiddleware, redis_client=redis_client, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(ServiceError)
    async def handle_service_error(_: Request, error: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": {"code": error.code, "message": error.message}},
        )

    app.include_router(router, prefix="/api/v1")
    app.include_router(role_router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await redis_client.aclose()
        await engine.dispose()

    return app


app = create_app()
