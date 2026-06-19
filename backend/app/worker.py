"""
app/worker.py
──────────────────────────────────────────────────────────────────────────────
ARQ Background Worker Configuration.

Jobs:
  - `export_suppliers_job`: Generates Excel export for > 5000 rows,
     uploads result to MinIO, and stores the download URL in Redis
     so the frontend can poll for completion.

Worker startup/shutdown hooks connect to Postgres and MinIO.
The worker is launched via: `python -m arq app.worker.WorkerSettings`
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import arq
from arq import ArqRedis
from arq.connections import RedisSettings

from app.core.config import settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

# ── ARQ Redis connection settings ─────────────────────────────────────────────
def get_arq_redis_settings() -> RedisSettings:
    return RedisSettings(
        host=settings.redis.REDIS_HOST,
        port=settings.redis.REDIS_PORT,
        password=settings.redis.REDIS_PASSWORD,
        database=settings.redis.REDIS_DB,
    )


# ── Job: Export Suppliers to Excel ────────────────────────────────────────────
async def export_suppliers_job(
    ctx: dict[str, Any],
    filters_dict: dict[str, Any],
    actor_id: str,
    task_id: str,
) -> dict[str, Any]:
    """
    ARQ background job: Generate and upload supplier Excel export.

    Flow:
      1. Deserialise filter params.
      2. Fetch all matching suppliers (no pagination limit).
      3. Generate XLSX with openpyxl.
      4. Upload XLSX to MinIO exports bucket.
      5. Generate presigned download URL.
      6. Store result in Redis with task_id key.
      7. Return result dict for ARQ job result storage.

    Args:
        ctx: ARQ context (contains db session, minio service).
        filters_dict: Serialised SupplierFilter dict.
        actor_id: ID of the user who requested the export.
        task_id: Unique task ID used by the frontend to poll status.

    Returns:
        Dict with `download_url` and `filename`.
    """
    from app.core.database import get_db_session_context
    from app.repositories.supplier_repository import SupplierRepository
    from app.schemas.supplier import SupplierFilter
    from app.services.export_service import generate_supplier_excel
    from app.services.minio_service import MinIOService

    logger.info("export_job_started", task_id=task_id, actor_id=actor_id)

    redis: ArqRedis = ctx["redis"]
    result_key = f"export_task:{task_id}"

    try:
        # Mark job as running in Redis
        await redis.set(result_key, "running", ex=3600)

        filters = SupplierFilter(**filters_dict)
        minio = MinIOService()

        async with get_db_session_context() as db:
            repo = SupplierRepository(db)
            suppliers = await repo.list_for_export(filters)

        logger.info("export_fetched_suppliers", count=len(suppliers), task_id=task_id)

        # Generate Excel
        xlsx_bytes = generate_supplier_excel(suppliers)

        # Upload to MinIO
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"supplier_export_{timestamp}_{task_id[:8]}.xlsx"
        object_key = minio.upload_export(xlsx_bytes, filename)

        # Generate presigned URL (24 hours)
        download_url = minio.generate_presigned_url(
            bucket=settings.minio.MINIO_BUCKET_EXPORTS,
            object_key=object_key,
            expiry_seconds=settings.minio.EXPORT_PRESIGNED_URL_EXPIRY_SECONDS,
        )

        result = {
            "status": "completed",
            "download_url": download_url,
            "filename": filename,
            "row_count": len(suppliers),
            "completed_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        # Store final result in Redis (24-hour TTL)
        import json
        await redis.set(result_key, json.dumps(result), ex=86400)

        logger.info(
            "export_job_completed",
            task_id=task_id,
            row_count=len(suppliers),
            filename=filename,
        )

        return result

    except Exception as e:
        error_result = {
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        import json
        await redis.set(result_key, json.dumps(error_result), ex=3600)
        logger.error("export_job_failed", task_id=task_id, error=str(e))
        raise


# ── Worker Startup / Shutdown Hooks ──────────────────────────────────────────
async def startup(ctx: dict[str, Any]) -> None:
    """Called once when the worker process starts."""
    configure_logging()
    logger.info(
        "worker_started",
        redis_host=settings.redis.REDIS_HOST,
        env=settings.APP_ENV,
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    """Called once when the worker process shuts down."""
    logger.info("worker_shutdown")


# ── ARQ WorkerSettings ────────────────────────────────────────────────────────
class WorkerSettings:
    """
    ARQ worker settings class.
    Referenced in docker-compose CMD: `python -m arq app.worker.WorkerSettings`
    """

    functions = [export_suppliers_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_arq_redis_settings()
    max_jobs = settings.arq.ARQ_MAX_JOBS
    job_timeout = settings.arq.ARQ_JOB_TIMEOUT
    # Retry failed jobs up to 3 times with exponential backoff
    max_tries = 3
    health_check_interval = 60
    health_check_key = "arq:health-check"
