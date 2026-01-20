"""
Water Treatment Controller - API v1 Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from fastapi import APIRouter

from .alarms import router as alarms_router
from .auth import router as auth_router
from .backup import router as backup_router
from .demo import router as demo_router
from .discover import router as discover_router
from .metrics import router as metrics_router
from .modbus import router as modbus_router
from .rtus import router as rtus_router
from .system import router as system_router
from .templates import router as templates_router
from .trends import router as trends_router
from .trends_optimized import router as trends_optimized_router
from .users import router as users_router

api_router = APIRouter()

# Auth routes - no prefix for /auth/login, /auth/logout, /auth/session
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])

# User management routes - admin only
api_router.include_router(users_router, prefix="/users", tags=["User Management"])

# Resource routes
api_router.include_router(rtus_router, prefix="/rtus", tags=["RTU Management"])
api_router.include_router(alarms_router, prefix="/alarms", tags=["Alarm Management"])
api_router.include_router(trends_router, prefix="/trends", tags=["Historian/Trends"])
api_router.include_router(trends_optimized_router, prefix="/trends", tags=["Historian/Trends"])
api_router.include_router(discover_router, prefix="/discover", tags=["Network Discovery"])
api_router.include_router(modbus_router, prefix="/modbus", tags=["Modbus Gateway"])
api_router.include_router(system_router, prefix="/system", tags=["System"])
api_router.include_router(backup_router, prefix="/backup", tags=["Backup/Restore"])
api_router.include_router(templates_router, prefix="/templates", tags=["Configuration Templates"])

# Demo mode for E2E testing and training
api_router.include_router(demo_router, prefix="/demo", tags=["Demo Mode"])

# Metrics/monitoring - no prefix, uses /metrics directly
api_router.include_router(metrics_router, tags=["Metrics"])

__all__ = ["api_router"]
