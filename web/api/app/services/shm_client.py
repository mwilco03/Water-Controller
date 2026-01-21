"""
Water Treatment Controller - Shared Memory Client Wrapper
Copyright (C) 2024-2025
SPDX-License-Identifier: GPL-3.0-or-later

Re-exports shared memory client functions from the package root for
internal app module imports.

Usage:
    from ...services.shm_client import get_shm_client
    shm = get_shm_client()
"""

# Use absolute import - shm_client.py is at the package root (/app/)
from shm_client import (
    WtcShmClient,
    WtcShmClientWithCircuitBreaker,
    get_client,
    get_resilient_client,
)


def get_shm_client() -> WtcShmClient:
    """
    Get or create shared memory client.

    Alias for get_client() to match expected import name.
    """
    return get_client()


__all__ = [
    "WtcShmClient",
    "WtcShmClientWithCircuitBreaker",
    "get_client",
    "get_shm_client",
    "get_resilient_client",
]
