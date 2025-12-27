"""
Water Treatment Controller - FastAPI Application
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Main FastAPI application entry point with new modular structure.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core.exceptions import ScadaException
from .core.errors import scada_exception_handler, generic_exception_handler
from .core.logging import setup_logging, get_logger
from .models.base import Base, engine
from .api.v1 import api_router
from .api.websocket import router as websocket_router
from .persistence.base import initialize as init_persistence
from .persistence.users import ensure_default_admin

# Setup logging
LOG_LEVEL = os.environ.get("WTC_LOG_LEVEL", "INFO")
LOG_STRUCTURED = os.environ.get("WTC_LOG_STRUCTURED", "false").lower() == "true"
setup_logging(level=LOG_LEVEL, structured=LOG_STRUCTURED)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    # Startup
    logger.info("Starting Water Treatment Controller API")

    # Create database tables (SQLAlchemy ORM)
    Base.metadata.create_all(bind=engine)
    logger.info("SQLAlchemy tables initialized")

    # Initialize persistence layer (SQLite direct) for auth/sessions
    init_persistence()
    logger.info("Persistence layer initialized")

    # Ensure default admin user exists
    ensure_default_admin()
    logger.info("Default admin user verified")

    yield

    # Shutdown
    logger.info("Shutting down Water Treatment Controller API")


# Create FastAPI application
app = FastAPI(
    title="Water Treatment Controller API",
    description="PROFINET IO Controller Backend for Water Treatment SCADA",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to each request for tracing."""
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    return response


# Exception handlers
app.add_exception_handler(ScadaException, scada_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


# Include routers
app.include_router(api_router, prefix="/api/v1")
app.include_router(websocket_router, prefix="/api/v1")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Water Treatment Controller API",
        "version": "2.0.0",
        "docs": "/api/docs",
        "health": "/health",
    }
