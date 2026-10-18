"""FastAPI application.

Run with the factory so settings are read at start-up, not at import:

    .venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
"""

import logging

import psycopg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.audits import router as audits_router
from app.api.v1.audits import ws_router
from app.core.config import Settings, get_settings
from app.db.repository import DatabaseConfigurationError

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(psycopg.OperationalError)
    async def database_unavailable(request: Request, exc: psycopg.OperationalError):
        logger.error("database unavailable: %s", type(exc).__name__)
        return JSONResponse({"detail": "The database is unavailable."}, status_code=503)

    @app.exception_handler(psycopg.Error)
    async def database_error(request: Request, exc: psycopg.Error):
        logger.error("database error: %s", type(exc).__name__)
        return JSONResponse({"detail": "A database error occurred."}, status_code=500)

    @app.exception_handler(DatabaseConfigurationError)
    async def database_not_configured(request: Request, exc: DatabaseConfigurationError):
        return JSONResponse({"detail": "The database is not configured."}, status_code=503)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(audits_router)
    app.include_router(ws_router)
    return app
