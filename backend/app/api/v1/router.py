"""
app/api/v1/router.py
──────────────────────────────────────────────────────────────────────────────
Master API v1 router — aggregates all sub-routers.
Mounted at `/api/v1` in `app/main.py`.
"""

from fastapi import APIRouter

from app.api.v1.routers.audit_logs import router as audit_logs_router
from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.bot_config import router as bot_config_router
from app.api.v1.routers.export import router as export_router
from app.api.v1.routers.supplier_documents import router as documents_router
from app.api.v1.routers.suppliers import router as suppliers_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router)
api_v1_router.include_router(suppliers_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(audit_logs_router)
api_v1_router.include_router(export_router)
api_v1_router.include_router(bot_config_router)
