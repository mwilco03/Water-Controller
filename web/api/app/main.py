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
from .core.logging import (
    setup_logging,
    get_logger,
    set_correlation_id,
    get_correlation_id,
    start_operation,
    end_operation,
)
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


# Correlation ID middleware
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    """Add correlation ID to each request for distributed tracing."""
    # Check for incoming correlation ID from client or upstream service
    # Support both X-Correlation-ID (preferred) and X-Request-ID (legacy)
    correlation_id = (
        request.headers.get("X-Correlation-ID") or
        request.headers.get("X-Request-ID") or
        str(uuid4())
    )

    # Store in request state for access in route handlers
    request.state.correlation_id = correlation_id
    request.state.request_id = correlation_id  # Legacy compatibility

    # Set correlation ID for logging context
    set_correlation_id(correlation_id)

    # Log request start
    logger.debug(
        f"Request started: {request.method} {request.url.path}",
        extra={"correlation_id": correlation_id}
    )

    try:
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Request-ID"] = correlation_id  # Legacy compatibility

        return response
    finally:
        # Clear correlation ID after request completes
        set_correlation_id(None)


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
