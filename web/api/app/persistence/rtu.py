"""
Water Treatment Controller - RTU Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

RTU device, sensor, and control operations using SQLAlchemy.

Note: Uses DictSerializableMixin.to_dict() from models/base.py for serialization.
"""

from datetime import UTC, datetime
from typing import Any

from ..core.config import settings
from ..models.legacy import RtuControl, RtuDevice, RtuSensor
from .audit import log_audit
from .base import get_db


# ============== RTU Device Operations ==============

def get_rtu_devices() -> list[dict[str, Any]]:
    """Get all RTU devices"""
    with get_db() as db:
        devices = db.query(RtuDevice).order_by(RtuDevice.station_name).all()
        return [d.to_dict() for d in devices]


def get_rtu_device(station_name: str) -> dict[str, Any] | None:
    """Get a single RTU device"""
    with get_db() as db:
        device = db.query(RtuDevice).filter(
            RtuDevice.station_name == station_name
        ).first()
        return device.to_dict() if device else None


def create_rtu_device(device: dict[str, Any]) -> int:
    """Create a new RTU device"""
    defaults = settings.rtu_defaults
    with get_db() as db:
        new_device = RtuDevice(
            station_name=device['station_name'],
            ip_address=device['ip_address'],
            vendor_id=device.get('vendor_id', defaults.VENDOR_ID),
            device_id=device.get('device_id', defaults.DEVICE_ID),
            slot_count=device.get('slot_count', defaults.SLOT_COUNT),
        )
        db.add(new_device)
        db.commit()
        db.refresh(new_device)
        log_audit('system', 'create', 'rtu_device', device['station_name'],
                  f"Created RTU {device['station_name']}")
        return new_device.id


def update_rtu_device(station_name: str, device: dict[str, Any]) -> bool:
    """Update an RTU device"""
    defaults = settings.rtu_defaults
    with get_db() as db:
        existing = db.query(RtuDevice).filter(
            RtuDevice.station_name == station_name
        ).first()
        if not existing:
            return False

        existing.ip_address = device['ip_address']
        existing.vendor_id = device.get('vendor_id', defaults.VENDOR_ID)
        existing.device_id = device.get('device_id', defaults.DEVICE_ID)
        existing.slot_count = device.get('slot_count', defaults.SLOT_COUNT)
        existing.updated_at = datetime.now(UTC)

        db.commit()
        return True


def delete_rtu_device(station_name: str) -> bool:
    """Delete an RTU device and all related configurations"""
    with get_db() as db:
        # Delete related records first
        db.query(RtuSensor).filter(RtuSensor.rtu_station == station_name).delete()
        db.query(RtuControl).filter(RtuControl.rtu_station == station_name).delete()

        # Delete the RTU device
        device = db.query(RtuDevice).filter(
            RtuDevice.station_name == station_name
        ).first()
        if not device:
            return False

        db.delete(device)
        db.commit()
        log_audit('system', 'delete', 'rtu_device', station_name,
                  f"Deleted RTU {station_name} with cascade")
        return True


# ============== RTU Sensors Operations ==============

def get_rtu_sensors(rtu_station: str) -> list[dict[str, Any]]:
    """Get all sensors for an RTU"""
    with get_db() as db:
        sensors = db.query(RtuSensor).filter(
            RtuSensor.rtu_station == rtu_station
        ).order_by(RtuSensor.sensor_id).all()
        return [s.to_dict() for s in sensors]


def upsert_rtu_sensor(sensor: dict[str, Any]) -> int:
    """Insert or update an RTU sensor"""
    with get_db() as db:
        existing = db.query(RtuSensor).filter(
            RtuSensor.rtu_station == sensor['rtu_station'],
            RtuSensor.sensor_id == sensor['sensor_id']
        ).first()

        if existing:
            existing.sensor_type = sensor['sensor_type']
            existing.name = sensor['name']
            existing.unit = sensor.get('unit')
            existing.register_address = sensor.get('register_address')
            existing.data_type = sensor.get('data_type', 'FLOAT32')
            existing.scale_min = sensor.get('scale_min', 0)
            existing.scale_max = sensor.get('scale_max', 100)
            db.commit()
            return existing.id
        else:
            new_sensor = RtuSensor(
                rtu_station=sensor['rtu_station'],
                sensor_id=sensor['sensor_id'],
                sensor_type=sensor['sensor_type'],
                name=sensor['name'],
                unit=sensor.get('unit'),
                register_address=sensor.get('register_address'),
                data_type=sensor.get('data_type', 'FLOAT32'),
                scale_min=sensor.get('scale_min', 0),
                scale_max=sensor.get('scale_max', 100),
            )
            db.add(new_sensor)
            db.commit()
            db.refresh(new_sensor)
            return new_sensor.id


def update_sensor_value(rtu_station: str, sensor_id: str, value: float, quality: int = 0) -> bool:
    """Update the last value for a sensor"""
    with get_db() as db:
        sensor = db.query(RtuSensor).filter(
            RtuSensor.rtu_station == rtu_station,
            RtuSensor.sensor_id == sensor_id
        ).first()
        if not sensor:
            return False
        sensor.last_value = value
        sensor.last_quality = quality
        sensor.last_update = datetime.now(UTC)
        db.commit()
        return True


def delete_rtu_sensor(rtu_station: str, sensor_id: str) -> bool:
    """Delete an RTU sensor"""
    with get_db() as db:
        sensor = db.query(RtuSensor).filter(
            RtuSensor.rtu_station == rtu_station,
            RtuSensor.sensor_id == sensor_id
        ).first()
        if not sensor:
            return False
        db.delete(sensor)
        db.commit()
        return True


def clear_rtu_sensors(rtu_station: str) -> int:
    """Clear all sensors for an RTU (before inventory refresh)"""
    with get_db() as db:
        count = db.query(RtuSensor).filter(
            RtuSensor.rtu_station == rtu_station
        ).delete()
        db.commit()
        return count


# ============== RTU Controls Operations ==============

def get_rtu_controls(rtu_station: str) -> list[dict[str, Any]]:
    """Get all controls for an RTU"""
    with get_db() as db:
        controls = db.query(RtuControl).filter(
            RtuControl.rtu_station == rtu_station
        ).order_by(RtuControl.control_id).all()
        return [c.to_dict() for c in controls]


def upsert_rtu_control(control: dict[str, Any]) -> int:
    """Insert or update an RTU control"""
    with get_db() as db:
        existing = db.query(RtuControl).filter(
            RtuControl.rtu_station == control['rtu_station'],
            RtuControl.control_id == control['control_id']
        ).first()

        if existing:
            existing.control_type = control['control_type']
            existing.name = control['name']
            existing.command_type = control.get('command_type', 'on_off')
            existing.register_address = control.get('register_address')
            existing.feedback_register = control.get('feedback_register')
            existing.range_min = control.get('range_min')
            existing.range_max = control.get('range_max')
            existing.unit = control.get('unit')
            db.commit()
            return existing.id
        else:
            new_control = RtuControl(
                rtu_station=control['rtu_station'],
                control_id=control['control_id'],
                control_type=control['control_type'],
                name=control['name'],
                command_type=control.get('command_type', 'on_off'),
                register_address=control.get('register_address'),
                feedback_register=control.get('feedback_register'),
                range_min=control.get('range_min'),
                range_max=control.get('range_max'),
                unit=control.get('unit'),
            )
            db.add(new_control)
            db.commit()
            db.refresh(new_control)
            return new_control.id


def update_control_state(rtu_station: str, control_id: str, state: str) -> bool:
    """Update the last state for a control"""
    with get_db() as db:
        control = db.query(RtuControl).filter(
            RtuControl.rtu_station == rtu_station,
            RtuControl.control_id == control_id
        ).first()
        if not control:
            return False
        control.last_state = state
        control.last_update = datetime.now(UTC)
        db.commit()
        return True


def delete_rtu_control(rtu_station: str, control_id: str) -> bool:
    """Delete an RTU control"""
    with get_db() as db:
        control = db.query(RtuControl).filter(
            RtuControl.rtu_station == rtu_station,
            RtuControl.control_id == control_id
        ).first()
        if not control:
            return False
        db.delete(control)
        db.commit()
        return True


def clear_rtu_controls(rtu_station: str) -> int:
    """Clear all controls for an RTU (before inventory refresh)"""
    with get_db() as db:
        count = db.query(RtuControl).filter(
            RtuControl.rtu_station == rtu_station
        ).delete()
        db.commit()
        return count


def get_rtu_inventory(rtu_station: str) -> dict[str, Any] | None:
    """Get complete inventory for an RTU (sensors + controls)"""
    device = get_rtu_device(rtu_station)
    if not device:
        return None

    return {
        "rtu_station": rtu_station,
        "device": device,
        "sensors": get_rtu_sensors(rtu_station),
        "controls": get_rtu_controls(rtu_station)
    }
