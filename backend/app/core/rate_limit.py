"""
app/core/rate_limit.py
──────────────────────────────────────────────────────────────────────────────
Global Rate Limiter configuration for SlowAPI.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit.RATE_LIMIT_DEFAULT],
    storage_uri=settings.redis.REDIS_URL,
)
