"""
Water Treatment Controller - Demo Mode API Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Endpoints for controlling demonstration mode for E2E testing,
training, and demos without real PROFINET hardware.
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...core.errors import build_success_response
from ...services.demo_mode import DemoScenario, get_demo_service

router = APIRouter()


class DemoEnableRequest(BaseModel):
    """Request to enable demo mode."""

    scenario: str = Field(
        "water_treatment_plant",
        description="Demo scenario: normal, startup, alarms, high_load, maintenance, water_treatment_plant"
    )


class DemoStatusResponse(BaseModel):
    """Demo mode status response."""

    enabled: bool
    scenario: str | None
    uptime_seconds: float
    rtu_count: int
    alarm_count: int
    pid_loop_count: int


@router.get("/status")
async def get_demo_status() -> dict[str, Any]:
    """
    Get current demo mode status.

    Returns whether demo mode is enabled, active scenario, and statistics.
    """
    demo = get_demo_service()
    status = demo.get_status()

    return build_success_response(DemoStatusResponse(
        enabled=status["enabled"],
        scenario=status["scenario"],
        uptime_seconds=status["uptime_seconds"],
        rtu_count=status["rtu_count"],
        alarm_count=status["alarm_count"],
        pid_loop_count=status["pid_loop_count"],
    ).model_dump())


@router.post("/enable")
async def enable_demo_mode(request: DemoEnableRequest) -> dict[str, Any]:
    """
    Enable demonstration mode with specified scenario.

    Demo mode provides realistic simulated data for testing,
    training, and demonstrations without real PROFINET hardware.

    **Available Scenarios:**
    - `normal`: Stable operation with minor variations
    - `startup`: RTUs connecting, systems initializing
    - `alarms`: Various alarm conditions triggered
    - `high_load`: System near capacity limits
    - `maintenance`: Some RTUs offline for maintenance
    - `water_treatment_plant`: Full water treatment facility demo

    **Environment Variable:**
    Can also be enabled via `WTC_DEMO_MODE=1` and `WTC_DEMO_SCENARIO=<scenario>`
    """
    demo = get_demo_service()

    try:
        scenario = DemoScenario(request.scenario)
    except ValueError:
        valid = [s.value for s in DemoScenario]
        return build_success_response({
            "success": False,
            "error": f"Invalid scenario. Valid options: {', '.join(valid)}",
        })

    demo.enable(scenario)

    return build_success_response({
        "success": True,
        "scenario": scenario.value,
        "message": f"Demo mode enabled with '{scenario.value}' scenario",
        **demo.get_status(),
    })


@router.post("/disable")
async def disable_demo_mode() -> dict[str, Any]:
    """
    Disable demonstration mode.

    Returns the system to normal operation mode where it will
    attempt to connect to the real C controller via shared memory.
    """
    demo = get_demo_service()
    was_enabled = demo.enabled
    demo.disable()

    return build_success_response({
        "success": True,
        "was_enabled": was_enabled,
        "message": "Demo mode disabled",
    })


@router.get("/scenarios")
async def list_scenarios() -> dict[str, Any]:
    """
    List available demo scenarios with descriptions.
    """
    scenarios = {
        "normal": {
            "name": "Normal Operation",
            "description": "Stable operation with minor sensor variations. Good for UI testing.",
            "rtus": 1,
            "features": ["Basic sensors", "PID loop", "Normal values"],
        },
        "startup": {
            "name": "Startup Sequence",
            "description": "Simulates system startup with RTUs connecting.",
            "rtus": 1,
            "features": ["Connecting RTU", "Transitioning states"],
        },
        "alarms": {
            "name": "Alarm Conditions",
            "description": "Various alarm conditions are triggered for testing alarm handling.",
            "rtus": 1,
            "features": ["High/low alarms", "Active alarms", "Alarm acknowledgment"],
        },
        "high_load": {
            "name": "High Load",
            "description": "System operating near capacity with values near alarm thresholds.",
            "rtus": 5,
            "features": ["Near-limit values", "Stress testing", "Edge cases"],
        },
        "maintenance": {
            "name": "Maintenance Mode",
            "description": "Some RTUs are offline for scheduled maintenance.",
            "rtus": 5,
            "features": ["Offline RTUs", "Partial operation", "Maintenance workflow"],
        },
        "water_treatment_plant": {
            "name": "Water Treatment Plant",
            "description": "Full water treatment facility with intake, clarifier, filters, disinfection, and distribution.",
            "rtus": 5,
            "features": [
                "Intake monitoring (flow, turbidity, pH, level)",
                "Clarifier (turbidity, sludge, coagulant)",
                "Filters (turbidity, pressure, flow)",
                "Disinfection (chlorine residual, contact time)",
                "Distribution (clearwell level, pressure, flow)",
                "3 PID control loops",
                "Realistic alarm conditions",
            ],
        },
    }

    return build_success_response({
        "scenarios": scenarios,
        "default": "water_treatment_plant",
    })


@router.get("/rtus")
async def get_demo_rtus() -> dict[str, Any]:
    """
    Get all RTUs in the current demo scenario.

    Returns real-time simulated data for all configured RTUs.
    """
    demo = get_demo_service()

    if not demo.enabled:
        return build_success_response({
            "enabled": False,
            "message": "Demo mode is not enabled",
            "rtus": [],
        })

    rtus = demo.get_rtus()

    return build_success_response({
        "enabled": True,
        "scenario": demo.scenario.value,
        "rtus": rtus,
    })


@router.get("/alarms")
async def get_demo_alarms() -> dict[str, Any]:
    """
    Get all active alarms in the demo scenario.
    """
    demo = get_demo_service()

    if not demo.enabled:
        return build_success_response({
            "enabled": False,
            "message": "Demo mode is not enabled",
            "alarms": [],
        })

    alarms = demo.get_alarms()

    return build_success_response({
        "enabled": True,
        "alarms": alarms,
        "count": len(alarms),
    })


@router.get("/pid")
async def get_demo_pid_loops() -> dict[str, Any]:
    """
    Get all PID loops in the demo scenario.
    """
    demo = get_demo_service()

    if not demo.enabled:
        return build_success_response({
            "enabled": False,
            "message": "Demo mode is not enabled",
            "pid_loops": [],
        })

    loops = demo.get_pid_loops()

    return build_success_response({
        "enabled": True,
        "pid_loops": loops,
        "count": len(loops),
    })
