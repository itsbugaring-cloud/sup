"""
app/main.py
──────────────────────────────────────────────────────────────────────────────
FastAPI application factory.

Features configured here:
  - Structlog JSON logging setup.
  - CORS middleware (origins from settings).
  - Request ID middleware (injects X-Request-ID into every request).
  - SlowAPI rate limiting (global limiter with Redis backend).
  - Exception handlers (structured error responses).
  - Lifespan context manager (DB engine ping, Redis health check).
  - API v1 router mounting.
  - OpenAPI docs (disabled in production).
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.

    Startup:
      - Configure structured logging.
      - Ping PostgreSQL (fail fast if DB is unreachable).
      - Ping Redis.

    Shutdown:
      - Dispose the SQLAlchemy engine connection pool.
    """
    configure_logging()
    logger.info(
        "app_starting",
        env=settings.APP_ENV,
        version=settings.APP_VERSION,
        api_prefix=settings.API_V1_PREFIX,
    )

    # ── DB health check on startup ────────────────────────────────────────────
    from app.core.database import engine
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("database_connected", host=settings.db.POSTGRES_HOST)
    except Exception as e:
        logger.error("database_connection_failed", error=str(e))
        raise

    # ── Redis health check & Cache init ───────────────────────────────────────
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis.REDIS_URL, encoding="utf8", decode_responses=False)
        await r.ping()
        FastAPICache.init(RedisBackend(r), prefix="fastapi-cache")
        logger.info("redis_connected_and_cache_initialized", host=settings.redis.REDIS_HOST)
    except Exception as e:
        logger.error("redis_connection_failed", error=str(e))
        raise

    logger.info("app_started")

    yield  # Application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    from app.core.database import engine
    await engine.dispose()
    logger.info("app_shutdown_complete")


# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit.RATE_LIMIT_DEFAULT],
    storage_uri=settings.redis.REDIS_URL,
)


# ── Application Factory ───────────────────────────────────────────────────────
def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Production-grade Supplier CRM API. "
            "Manage suppliers, documents, and audit logs."
        ),
        # Disable docs in production
        docs_url="/api/docs" if not settings.IS_PRODUCTION else None,
        redoc_url="/api/redoc" if not settings.IS_PRODUCTION else None,
        openapi_url="/api/openapi.json" if not settings.IS_PRODUCTION else None,
        lifespan=lifespan,
    )

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS_LIST,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Row-Count"],
    )

    # ── Request ID Middleware ─────────────────────────────────────────────────
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Inject request_id into structlog context for this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        response.headers["X-Request-ID"] = request_id

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        return response

    # ── Exception Handlers ────────────────────────────────────────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Return structured validation errors matching our ErrorResponse schema."""
        from app.schemas.common import ErrorDetail, ErrorResponse

        errors = [
            ErrorDetail(
                field=".".join(str(loc) for loc in e["loc"]),
                message=e["msg"],
                code=e["type"],
            )
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                message="Validation error",
                errors=errors,
                request_id=getattr(request.state, "request_id", None),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all handler — logs the error and returns a generic 500."""
        from app.schemas.common import ErrorResponse

        logger.error(
            "unhandled_exception",
            error=str(exc),
            exc_info=True,
            path=request.url.path,
        )

        if settings.IS_PRODUCTION:
            # Never expose internal errors in production
            message = "An internal server error occurred"
        else:
            message = str(exc)

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                message=message,
                request_id=getattr(request.state, "request_id", None),
            ).model_dump(),
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

    # ── Health & Readiness Endpoints ─────────────────────────────────────────
    @app.get("/api/v1/health", tags=["health"], include_in_schema=False)
    async def health_check() -> dict:
        return {"status": "ok", "version": settings.APP_VERSION}

    @app.get("/api/v1/readiness", tags=["health"], include_in_schema=False)
    async def readiness_check() -> dict:
        """Deep health check — verifies DB and Redis connectivity."""
        from app.core.database import engine
        from sqlalchemy import text
        import redis.asyncio as aioredis

        db_ok = False
        redis_ok = False

        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            pass

        try:
            r = aioredis.from_url(settings.redis.REDIS_URL)
            await r.ping()
            await r.aclose()
            redis_ok = True
        except Exception:
            pass

        all_ok = db_ok and redis_ok
        return {
            "status": "ready" if all_ok else "degraded",
            "postgres": "ok" if db_ok else "unavailable",
            "redis": "ok" if redis_ok else "unavailable",
        }

    # ── Serve Frontend (Static CDN app) ──────────────────────────────────────
    import os
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


# ── Module-level app instance (referenced by Uvicorn CMD) ────────────────────
app = create_application()
