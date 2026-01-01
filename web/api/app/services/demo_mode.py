"""
Water Treatment Controller - Demonstration Mode Service
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Provides realistic mock data for E2E testing, demos, and operator training
without requiring real PROFINET hardware or the C controller.

Usage:
    from app.services.demo_mode import get_demo_service, DemoMode

    demo = get_demo_service()
    demo.enable(scenario="water_treatment_plant")

    # Get simulated sensor values
    sensors = demo.get_sensor_values("rtu-01")
"""

import logging
import math
import os
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class DemoScenario(str, Enum):
    """Pre-defined demonstration scenarios."""

    NORMAL_OPERATION = "normal"           # Stable operation, minor variations
    STARTUP_SEQUENCE = "startup"          # RTUs connecting, systems initializing
    ALARM_CONDITIONS = "alarms"           # Various alarm conditions triggered
    HIGH_LOAD = "high_load"               # System under stress, near limits
    MAINTENANCE = "maintenance"           # Some RTUs offline for maintenance
    WATER_TREATMENT_PLANT = "water_treatment_plant"  # Full water treatment demo


@dataclass
class SimulatedSensor:
    """Configuration for a simulated sensor."""

    slot: int
    tag: str
    base_value: float
    unit: str
    noise_amplitude: float = 0.5      # Random noise range
    trend_amplitude: float = 0.0      # Sinusoidal trend amplitude
    trend_period: float = 300.0       # Trend period in seconds
    min_value: float = 0.0
    max_value: float = 100.0
    alarm_low: float | None = None
    alarm_high: float | None = None

    def get_value(self, t: float) -> float:
        """Generate simulated value at time t."""
        # Base value with trend
        trend = self.trend_amplitude * math.sin(2 * math.pi * t / self.trend_period)

        # Add random noise
        noise = random.uniform(-self.noise_amplitude, self.noise_amplitude)

        # Combine and clamp
        value = self.base_value + trend + noise
        return max(self.min_value, min(self.max_value, value))


@dataclass
class SimulatedActuator:
    """Configuration for a simulated actuator."""

    slot: int
    tag: str
    command: int = 0       # 0=OFF, 1=ON, 2=PWM
    pwm_duty: int = 0
    forced: bool = False


@dataclass
class SimulatedRTU:
    """Configuration for a simulated RTU."""

    station_name: str
    ip_address: str
    vendor_id: int = 0x0493
    device_id: int = 0x0001
    connection_state: int = 3  # RUNNING
    slot_count: int = 16
    sensors: list[SimulatedSensor] = field(default_factory=list)
    actuators: list[SimulatedActuator] = field(default_factory=list)
    packet_loss_percent: float = 0.01
    total_cycles: int = 0


@dataclass
class SimulatedAlarm:
    """A simulated active alarm."""

    alarm_id: int
    rule_id: int
    rtu_station: str
    slot: int
    severity: int
    state: int  # 0=cleared, 1=active, 2=acknowledged
    message: str
    value: float
    threshold: float
    raise_time_ms: int
    ack_time_ms: int = 0
    ack_user: str = ""


@dataclass
class SimulatedPidLoop:
    """A simulated PID control loop."""

    loop_id: int
    name: str
    enabled: bool = True
    input_rtu: str = ""
    input_slot: int = 0
    output_rtu: str = ""
    output_slot: int = 0
    kp: float = 1.0
    ki: float = 0.1
    kd: float = 0.05
    setpoint: float = 50.0
    pv: float = 50.0
    cv: float = 50.0
    mode: int = 1  # 0=MANUAL, 1=AUTO, 2=CASCADE

    # Internal state for simulation
    _integral: float = 0.0
    _last_error: float = 0.0
    _last_time: float = 0.0

    def update(self, pv: float, dt: float) -> float:
        """Update PID and return new control value."""
        if self.mode == 0:  # MANUAL
            return self.cv

        error = self.setpoint - pv
        self._integral += error * dt
        derivative = (error - self._last_error) / dt if dt > 0 else 0

        cv = self.kp * error + self.ki * self._integral + self.kd * derivative
        cv = max(0, min(100, cv))  # Clamp to 0-100

        self._last_error = error
        self.pv = pv
        self.cv = cv
        return cv


class DemoModeService:
    """
    Demonstration mode service providing realistic simulated data.

    Generates time-varying sensor values, manages simulated RTU states,
    creates realistic alarm conditions, and simulates PID control loops.
    """

    def __init__(self):
        self._enabled = False
        self._scenario: DemoScenario = DemoScenario.NORMAL_OPERATION
        self._start_time: float = 0.0
        self._rtus: dict[str, SimulatedRTU] = {}
        self._alarms: list[SimulatedAlarm] = []
        self._pid_loops: list[SimulatedPidLoop] = []
        self._alarm_id_counter = 1000
        self._lock = threading.Lock()
        self._update_thread: threading.Thread | None = None
        self._running = False

        # Check environment for auto-enable
        if os.environ.get("WTC_DEMO_MODE", "").lower() in ("1", "true", "yes"):
            scenario = os.environ.get("WTC_DEMO_SCENARIO", "normal")
            self.enable(DemoScenario(scenario))

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def scenario(self) -> DemoScenario:
        return self._scenario

    def enable(self, scenario: DemoScenario = DemoScenario.NORMAL_OPERATION) -> None:
        """Enable demonstration mode with specified scenario."""
        with self._lock:
            self._enabled = True
            self._scenario = scenario
            self._start_time = time.time()
            self._setup_scenario(scenario)

            # Start background update thread
            if not self._running:
                self._running = True
                self._update_thread = threading.Thread(
                    target=self._update_loop,
                    daemon=True,
                    name="demo-mode-updater"
                )
                self._update_thread.start()

            logger.info(f"Demo mode enabled with scenario: {scenario.value}")

    def disable(self) -> None:
        """Disable demonstration mode."""
        with self._lock:
            self._enabled = False
            self._running = False
            self._rtus.clear()
            self._alarms.clear()
            self._pid_loops.clear()
            logger.info("Demo mode disabled")

    def get_status(self) -> dict[str, Any]:
        """Get demo mode status."""
        return {
            "enabled": self._enabled,
            "scenario": self._scenario.value if self._enabled else None,
            "uptime_seconds": time.time() - self._start_time if self._enabled else 0,
            "rtu_count": len(self._rtus),
            "alarm_count": len(self._alarms),
            "pid_loop_count": len(self._pid_loops),
        }

    def is_controller_running(self) -> bool:
        """Simulate controller running state."""
        return self._enabled

    def get_rtus(self) -> list[dict[str, Any]]:
        """Get all simulated RTUs."""
        if not self._enabled:
            return []

        t = time.time() - self._start_time
        result = []

        with self._lock:
            for rtu in self._rtus.values():
                sensors = []
                for sensor in rtu.sensors:
                    value = sensor.get_value(t)
                    sensors.append({
                        "slot": sensor.slot,
                        "value": round(value, 2),
                        "status": 0,  # GOOD
                        "quality": 0x00,  # GOOD
                        "timestamp_ms": int(time.time() * 1000),
                    })

                actuators = []
                for actuator in rtu.actuators:
                    actuators.append({
                        "slot": actuator.slot,
                        "command": actuator.command,
                        "pwm_duty": actuator.pwm_duty,
                        "forced": actuator.forced,
                    })

                result.append({
                    "station_name": rtu.station_name,
                    "ip_address": rtu.ip_address,
                    "vendor_id": rtu.vendor_id,
                    "device_id": rtu.device_id,
                    "connection_state": rtu.connection_state,
                    "slot_count": rtu.slot_count,
                    "sensors": sensors,
                    "actuators": actuators,
                    "packet_loss_percent": rtu.packet_loss_percent,
                    "total_cycles": rtu.total_cycles,
                })

        return result

    def get_rtu(self, station_name: str) -> dict[str, Any] | None:
        """Get a specific simulated RTU."""
        rtus = self.get_rtus()
        for rtu in rtus:
            if rtu["station_name"] == station_name:
                return rtu
        return None

    def get_sensors(self, station_name: str) -> list[dict[str, Any]]:
        """Get sensor values for an RTU."""
        rtu = self.get_rtu(station_name)
        if not rtu:
            return []
        return rtu.get("sensors", [])

    def get_actuators(self, station_name: str) -> list[dict[str, Any]]:
        """Get actuator states for an RTU."""
        rtu = self.get_rtu(station_name)
        if not rtu:
            return []
        return rtu.get("actuators", [])

    def get_alarms(self) -> list[dict[str, Any]]:
        """Get active alarms."""
        if not self._enabled:
            return []

        with self._lock:
            return [
                {
                    "alarm_id": a.alarm_id,
                    "rule_id": a.rule_id,
                    "rtu_station": a.rtu_station,
                    "slot": a.slot,
                    "severity": a.severity,
                    "state": a.state,
                    "message": a.message,
                    "value": a.value,
                    "threshold": a.threshold,
                    "raise_time_ms": a.raise_time_ms,
                    "ack_time_ms": a.ack_time_ms,
                    "ack_user": a.ack_user,
                }
                for a in self._alarms
                if a.state != 0  # Not cleared
            ]

    def get_pid_loops(self) -> list[dict[str, Any]]:
        """Get PID loop states."""
        if not self._enabled:
            return []

        with self._lock:
            return [
                {
                    "loop_id": loop.loop_id,
                    "name": loop.name,
                    "enabled": loop.enabled,
                    "input_rtu": loop.input_rtu,
                    "input_slot": loop.input_slot,
                    "output_rtu": loop.output_rtu,
                    "output_slot": loop.output_slot,
                    "kp": loop.kp,
                    "ki": loop.ki,
                    "kd": loop.kd,
                    "setpoint": loop.setpoint,
                    "pv": round(loop.pv, 2),
                    "cv": round(loop.cv, 2),
                    "mode": loop.mode,
                }
                for loop in self._pid_loops
            ]

    def dcp_discover(self, timeout_ms: int = 5000) -> list[dict[str, Any]]:
        """Simulate DCP discovery returning demo RTUs."""
        if not self._enabled:
            return []

        # Simulate discovery delay
        time.sleep(min(timeout_ms / 1000.0, 2.0))

        result = []
        with self._lock:
            for rtu in self._rtus.values():
                result.append({
                    "mac_address": f"00:1A:2B:{random.randint(0,255):02X}:{random.randint(0,255):02X}:{random.randint(0,255):02X}",
                    "ip_address": rtu.ip_address,
                    "device_name": rtu.station_name,
                    "vendor_name": "Demo-Vendor",
                    "device_type": "Water Treatment RTU",
                    "profinet_vendor_id": rtu.vendor_id,
                    "profinet_device_id": rtu.device_id,
                })

        return result

    def command_actuator(self, station: str, slot: int, command: int, pwm_duty: int = 0) -> bool:
        """Handle actuator command in demo mode."""
        with self._lock:
            rtu = self._rtus.get(station)
            if not rtu:
                return False

            for actuator in rtu.actuators:
                if actuator.slot == slot:
                    actuator.command = command
                    actuator.pwm_duty = pwm_duty
                    logger.info(f"[DEMO] Actuator command: {station}/{slot} = {command}")
                    return True

        return False

    def set_setpoint(self, loop_id: int, setpoint: float) -> bool:
        """Set PID loop setpoint in demo mode."""
        with self._lock:
            for loop in self._pid_loops:
                if loop.loop_id == loop_id:
                    loop.setpoint = setpoint
                    logger.info(f"[DEMO] Setpoint change: loop {loop_id} = {setpoint}")
                    return True
        return False

    def set_pid_mode(self, loop_id: int, mode: int) -> bool:
        """Set PID loop mode in demo mode."""
        with self._lock:
            for loop in self._pid_loops:
                if loop.loop_id == loop_id:
                    loop.mode = mode
                    logger.info(f"[DEMO] Mode change: loop {loop_id} = {mode}")
                    return True
        return False

    def acknowledge_alarm(self, alarm_id: int, user: str) -> bool:
        """Acknowledge alarm in demo mode."""
        with self._lock:
            for alarm in self._alarms:
                if alarm.alarm_id == alarm_id and alarm.state == 1:
                    alarm.state = 2  # ACKNOWLEDGED
                    alarm.ack_time_ms = int(time.time() * 1000)
                    alarm.ack_user = user
                    logger.info(f"[DEMO] Alarm acknowledged: {alarm_id} by {user}")
                    return True
        return False

    def _setup_scenario(self, scenario: DemoScenario) -> None:
        """Initialize scenario-specific demo data."""
        self._rtus.clear()
        self._alarms.clear()
        self._pid_loops.clear()

        if scenario == DemoScenario.WATER_TREATMENT_PLANT:
            self._setup_water_treatment_plant()
        elif scenario == DemoScenario.ALARM_CONDITIONS:
            self._setup_alarm_scenario()
        elif scenario == DemoScenario.STARTUP_SEQUENCE:
            self._setup_startup_scenario()
        elif scenario == DemoScenario.HIGH_LOAD:
            self._setup_high_load_scenario()
        elif scenario == DemoScenario.MAINTENANCE:
            self._setup_maintenance_scenario()
        else:  # NORMAL_OPERATION
            self._setup_normal_scenario()

    def _setup_water_treatment_plant(self) -> None:
        """Set up a full water treatment plant demo."""
        # Intake RTU
        intake = SimulatedRTU(
            station_name="intake-rtu-01",
            ip_address="192.168.1.10",
            sensors=[
                SimulatedSensor(slot=1, tag="RAW_FLOW", base_value=850, unit="GPM",
                              noise_amplitude=15, trend_amplitude=50, trend_period=600,
                              min_value=0, max_value=1200, alarm_low=100, alarm_high=1100),
                SimulatedSensor(slot=2, tag="RAW_TURB", base_value=12, unit="NTU",
                              noise_amplitude=2, trend_amplitude=3, trend_period=1800,
                              min_value=0, max_value=100, alarm_high=25),
                SimulatedSensor(slot=3, tag="RAW_PH", base_value=7.2, unit="pH",
                              noise_amplitude=0.1, trend_amplitude=0.2, trend_period=900,
                              min_value=0, max_value=14, alarm_low=6.5, alarm_high=8.5),
                SimulatedSensor(slot=4, tag="INTAKE_LEVEL", base_value=75, unit="%",
                              noise_amplitude=2, trend_amplitude=5, trend_period=1200,
                              min_value=0, max_value=100, alarm_low=20, alarm_high=95),
            ],
            actuators=[
                SimulatedActuator(slot=5, tag="INTAKE_VALVE", command=1),
                SimulatedActuator(slot=6, tag="INTAKE_PUMP", command=1),
            ]
        )
        self._rtus[intake.station_name] = intake

        # Clarifier RTU
        clarifier = SimulatedRTU(
            station_name="clarifier-rtu-01",
            ip_address="192.168.1.11",
            sensors=[
                SimulatedSensor(slot=1, tag="CLAR_TURB", base_value=3.5, unit="NTU",
                              noise_amplitude=0.5, trend_amplitude=1, trend_period=1200,
                              min_value=0, max_value=50, alarm_high=8),
                SimulatedSensor(slot=2, tag="SLUDGE_LEVEL", base_value=35, unit="%",
                              noise_amplitude=2, trend_amplitude=8, trend_period=3600,
                              min_value=0, max_value=100, alarm_high=75),
                SimulatedSensor(slot=3, tag="COAG_FLOW", base_value=15, unit="GPH",
                              noise_amplitude=1, trend_amplitude=2, trend_period=600,
                              min_value=0, max_value=50),
            ],
            actuators=[
                SimulatedActuator(slot=4, tag="COAG_PUMP", command=1),
                SimulatedActuator(slot=5, tag="FLOC_MIXER", command=1),
                SimulatedActuator(slot=6, tag="SLUDGE_VALVE", command=0),
            ]
        )
        self._rtus[clarifier.station_name] = clarifier

        # Filter RTU
        filters = SimulatedRTU(
            station_name="filter-rtu-01",
            ip_address="192.168.1.12",
            sensors=[
                SimulatedSensor(slot=1, tag="FILT_TURB", base_value=0.3, unit="NTU",
                              noise_amplitude=0.05, trend_amplitude=0.1, trend_period=1800,
                              min_value=0, max_value=10, alarm_high=1.0),
                SimulatedSensor(slot=2, tag="FILT_DP", base_value=8, unit="PSI",
                              noise_amplitude=0.5, trend_amplitude=2, trend_period=7200,
                              min_value=0, max_value=25, alarm_high=18),
                SimulatedSensor(slot=3, tag="FILT_FLOW", base_value=420, unit="GPM",
                              noise_amplitude=10, trend_amplitude=30, trend_period=900,
                              min_value=0, max_value=600),
            ],
            actuators=[
                SimulatedActuator(slot=4, tag="FILT_INLET", command=1),
                SimulatedActuator(slot=5, tag="BACKWASH", command=0),
            ]
        )
        self._rtus[filters.station_name] = filters

        # Disinfection RTU
        disinfection = SimulatedRTU(
            station_name="disinfect-rtu-01",
            ip_address="192.168.1.13",
            sensors=[
                SimulatedSensor(slot=1, tag="CL2_RESIDUAL", base_value=1.8, unit="mg/L",
                              noise_amplitude=0.1, trend_amplitude=0.3, trend_period=600,
                              min_value=0, max_value=5, alarm_low=0.5, alarm_high=4.0),
                SimulatedSensor(slot=2, tag="CL2_FLOW", base_value=2.5, unit="GPH",
                              noise_amplitude=0.2, trend_amplitude=0.5, trend_period=900,
                              min_value=0, max_value=10),
                SimulatedSensor(slot=3, tag="CONTACT_TIME", base_value=32, unit="min",
                              noise_amplitude=1, min_value=0, max_value=60, alarm_low=20),
            ],
            actuators=[
                SimulatedActuator(slot=4, tag="CL2_PUMP", command=2, pwm_duty=65),
            ]
        )
        self._rtus[disinfection.station_name] = disinfection

        # Clearwell/Distribution RTU
        distribution = SimulatedRTU(
            station_name="distrib-rtu-01",
            ip_address="192.168.1.14",
            sensors=[
                SimulatedSensor(slot=1, tag="CLEARWELL_LVL", base_value=82, unit="%",
                              noise_amplitude=1, trend_amplitude=8, trend_period=3600,
                              min_value=0, max_value=100, alarm_low=25, alarm_high=95),
                SimulatedSensor(slot=2, tag="DIST_PRESS", base_value=55, unit="PSI",
                              noise_amplitude=2, trend_amplitude=5, trend_period=1800,
                              min_value=0, max_value=100, alarm_low=35, alarm_high=80),
                SimulatedSensor(slot=3, tag="DIST_FLOW", base_value=780, unit="GPM",
                              noise_amplitude=20, trend_amplitude=100, trend_period=7200,
                              min_value=0, max_value=1500),
            ],
            actuators=[
                SimulatedActuator(slot=4, tag="HIGH_LIFT_1", command=1),
                SimulatedActuator(slot=5, tag="HIGH_LIFT_2", command=1),
                SimulatedActuator(slot=6, tag="DIST_VALVE", command=1),
            ]
        )
        self._rtus[distribution.station_name] = distribution

        # PID Loops
        self._pid_loops = [
            SimulatedPidLoop(
                loop_id=1, name="Chlorine Residual Control",
                input_rtu="disinfect-rtu-01", input_slot=1,
                output_rtu="disinfect-rtu-01", output_slot=4,
                kp=2.0, ki=0.5, kd=0.1,
                setpoint=1.8, pv=1.8, cv=65
            ),
            SimulatedPidLoop(
                loop_id=2, name="Clearwell Level Control",
                input_rtu="distrib-rtu-01", input_slot=1,
                output_rtu="filter-rtu-01", output_slot=4,
                kp=1.5, ki=0.2, kd=0.05,
                setpoint=80, pv=82, cv=70
            ),
            SimulatedPidLoop(
                loop_id=3, name="Distribution Pressure Control",
                input_rtu="distrib-rtu-01", input_slot=2,
                output_rtu="distrib-rtu-01", output_slot=4,
                kp=1.0, ki=0.3, kd=0.1,
                setpoint=55, pv=55, cv=75
            ),
        ]

    def _setup_normal_scenario(self) -> None:
        """Set up basic normal operation demo."""
        rtu = SimulatedRTU(
            station_name="demo-rtu-01",
            ip_address="192.168.1.100",
            sensors=[
                SimulatedSensor(slot=1, tag="TEMP_01", base_value=25, unit="°C",
                              noise_amplitude=0.5, trend_amplitude=2, trend_period=300),
                SimulatedSensor(slot=2, tag="PRESS_01", base_value=50, unit="PSI",
                              noise_amplitude=1, trend_amplitude=5, trend_period=600),
                SimulatedSensor(slot=3, tag="FLOW_01", base_value=100, unit="GPM",
                              noise_amplitude=3, trend_amplitude=10, trend_period=450),
                SimulatedSensor(slot=4, tag="LEVEL_01", base_value=75, unit="%",
                              noise_amplitude=1, trend_amplitude=5, trend_period=900),
            ],
            actuators=[
                SimulatedActuator(slot=5, tag="VALVE_01", command=1),
                SimulatedActuator(slot=6, tag="PUMP_01", command=1),
            ]
        )
        self._rtus[rtu.station_name] = rtu

        self._pid_loops = [
            SimulatedPidLoop(
                loop_id=1, name="Temperature Control",
                input_rtu="demo-rtu-01", input_slot=1,
                output_rtu="demo-rtu-01", output_slot=5,
                setpoint=25, pv=25, cv=50
            ),
        ]

    def _setup_alarm_scenario(self) -> None:
        """Set up scenario with various alarm conditions."""
        self._setup_normal_scenario()

        # Modify sensors to trigger alarms
        rtu = self._rtus.get("demo-rtu-01")
        if rtu and len(rtu.sensors) >= 2:
            # High temperature alarm
            rtu.sensors[0].base_value = 38
            rtu.sensors[0].alarm_high = 35

            # Low pressure alarm
            rtu.sensors[1].base_value = 15
            rtu.sensors[1].alarm_low = 20

        # Add initial alarms
        self._alarms = [
            SimulatedAlarm(
                alarm_id=self._alarm_id_counter,
                rule_id=1,
                rtu_station="demo-rtu-01",
                slot=1,
                severity=2,  # HIGH
                state=1,  # ACTIVE
                message="High temperature alarm",
                value=38.5,
                threshold=35.0,
                raise_time_ms=int((time.time() - 300) * 1000)
            ),
        ]
        self._alarm_id_counter += 1

    def _setup_startup_scenario(self) -> None:
        """Set up scenario simulating system startup."""
        self._setup_normal_scenario()

        # Set RTU to CONNECTING state initially
        rtu = self._rtus.get("demo-rtu-01")
        if rtu:
            rtu.connection_state = 1  # CONNECTING

    def _setup_high_load_scenario(self) -> None:
        """Set up scenario with system near capacity."""
        self._setup_water_treatment_plant()

        # Increase base values near alarm thresholds
        for rtu in self._rtus.values():
            for sensor in rtu.sensors:
                if sensor.alarm_high:
                    sensor.base_value = sensor.alarm_high * 0.9

    def _setup_maintenance_scenario(self) -> None:
        """Set up scenario with some RTUs offline."""
        self._setup_water_treatment_plant()

        # Set one RTU offline
        if "clarifier-rtu-01" in self._rtus:
            self._rtus["clarifier-rtu-01"].connection_state = 5  # OFFLINE

    def _update_loop(self) -> None:
        """Background thread for updating simulated values."""
        last_update = time.time()

        while self._running:
            time.sleep(1.0)  # Update every second

            if not self._enabled:
                continue

            now = time.time()
            dt = now - last_update
            last_update = now

            with self._lock:
                # Update cycle counters
                for rtu in self._rtus.values():
                    if rtu.connection_state == 3:  # RUNNING
                        rtu.total_cycles += 1

                # Update PID loops
                t = now - self._start_time
                for loop in self._pid_loops:
                    if loop.enabled and loop.input_rtu in self._rtus:
                        rtu = self._rtus[loop.input_rtu]
                        for sensor in rtu.sensors:
                            if sensor.slot == loop.input_slot:
                                pv = sensor.get_value(t)
                                loop.update(pv, dt)
                                break

                # Check for alarm conditions
                self._check_alarms()

    def _check_alarms(self) -> None:
        """Check sensor values and generate/clear alarms."""
        t = time.time() - self._start_time
        now_ms = int(time.time() * 1000)

        for rtu in self._rtus.values():
            if rtu.connection_state != 3:  # Not RUNNING
                continue

            for sensor in rtu.sensors:
                value = sensor.get_value(t)

                # Check high alarm
                if sensor.alarm_high and value > sensor.alarm_high:
                    self._raise_alarm(
                        rtu.station_name, sensor.slot, sensor.tag,
                        f"High {sensor.tag} alarm", value, sensor.alarm_high, 2
                    )
                elif sensor.alarm_high:
                    self._clear_alarm(rtu.station_name, sensor.slot, "high")

                # Check low alarm
                if sensor.alarm_low and value < sensor.alarm_low:
                    self._raise_alarm(
                        rtu.station_name, sensor.slot, sensor.tag,
                        f"Low {sensor.tag} alarm", value, sensor.alarm_low, 2
                    )
                elif sensor.alarm_low:
                    self._clear_alarm(rtu.station_name, sensor.slot, "low")

    def _raise_alarm(self, rtu: str, slot: int, tag: str, message: str,
                     value: float, threshold: float, severity: int) -> None:
        """Raise or update an alarm."""
        # Check if alarm already exists
        for alarm in self._alarms:
            if alarm.rtu_station == rtu and alarm.slot == slot and alarm.state != 0:
                alarm.value = value
                return

        # Create new alarm
        alarm = SimulatedAlarm(
            alarm_id=self._alarm_id_counter,
            rule_id=slot,
            rtu_station=rtu,
            slot=slot,
            severity=severity,
            state=1,  # ACTIVE
            message=message,
            value=round(value, 2),
            threshold=threshold,
            raise_time_ms=int(time.time() * 1000)
        )
        self._alarms.append(alarm)
        self._alarm_id_counter += 1
        logger.info(f"[DEMO] Alarm raised: {message} ({value:.2f} > {threshold})")

    def _clear_alarm(self, rtu: str, slot: int, alarm_type: str) -> None:
        """Clear an alarm if conditions return to normal."""
        for alarm in self._alarms:
            if alarm.rtu_station == rtu and alarm.slot == slot and alarm.state != 0:
                if alarm_type in alarm.message.lower():
                    alarm.state = 0  # CLEARED
                    logger.info(f"[DEMO] Alarm cleared: {alarm.message}")


# Global demo service instance
_demo_service: DemoModeService | None = None


def get_demo_service() -> DemoModeService:
    """Get or create the demo mode service."""
    global _demo_service
    if _demo_service is None:
        _demo_service = DemoModeService()
    return _demo_service
