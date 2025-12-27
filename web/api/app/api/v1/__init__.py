"""
Water Treatment Controller - API v1 Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from fastapi import APIRouter

from .auth import router as auth_router
from .rtus import router as rtus_router
from .alarms import router as alarms_router
from .trends import router as trends_router
from .discover import router as discover_router
from .system import router as system_router
from .backup import router as backup_router
from .templates import router as templates_router

api_router = APIRouter()

# Auth routes - no prefix for /auth/login, /auth/logout, /auth/session
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])

# Resource routes
api_router.include_router(rtus_router, prefix="/rtus", tags=["RTU Management"])
api_router.include_router(alarms_router, prefix="/alarms", tags=["Alarm Management"])
api_router.include_router(trends_router, prefix="/trends", tags=["Historian/Trends"])
api_router.include_router(discover_router, prefix="/discover", tags=["Network Discovery"])
api_router.include_router(system_router, prefix="/system", tags=["System"])
api_router.include_router(backup_router, prefix="/system", tags=["Backup/Restore"])
api_router.include_router(templates_router, prefix="/templates", tags=["Configuration Templates"])

__all__ = ["api_router"]
