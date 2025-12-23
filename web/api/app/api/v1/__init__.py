"""
Water Treatment Controller - API v1 Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from fastapi import APIRouter

from .rtus import router as rtus_router
from .slots import router as slots_router
from .sensors import router as sensors_router
from .controls import router as controls_router
from .profinet import router as profinet_router
from .alarms import router as alarms_router
from .trends import router as trends_router
from .discover import router as discover_router
from .system import router as system_router

api_router = APIRouter()

api_router.include_router(rtus_router, prefix="/rtus", tags=["RTU Management"])
api_router.include_router(alarms_router, prefix="/alarms", tags=["Alarm Management"])
api_router.include_router(trends_router, prefix="/trends", tags=["Historian/Trends"])
api_router.include_router(discover_router, prefix="/discover", tags=["Network Discovery"])
api_router.include_router(system_router, prefix="/system", tags=["System"])

__all__ = ["api_router"]
