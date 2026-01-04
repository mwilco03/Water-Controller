"""
Water Treatment Controller - RTU Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

RTU device, sensor, and control operations using SQLAlchemy ORM models.

Note: Uses DictSerializableMixin.to_dict() from models/base.py for serialization.
This module now uses the unified ORM models (RTU, Sensor, Control) instead of
the deprecated legacy models (RtuDevice, RtuSensor, RtuControl).
"""

from datetime import UTC, datetime
from typing import Any

from ..core.config import settings
from ..models.rtu import RTU, Control, RtuState, Sensor, Slot, SlotStatus
from .audit import log_audit
from .base import get_db


# ============== RTU Device Operations ==============

def get_rtu_devices() -> list[dict[str, Any]]:
    """Get all RTU devices."""
    with get_db() as db:
        devices = db.query(RTU).order_by(RTU.station_name).all()
        return [d.to_dict() for d in devices]


def get_rtu_device(station_name: str) -> dict[str, Any] | None:
    """Get a single RTU device."""
    with get_db() as db:
        device = db.query(RTU).filter(
            RTU.station_name == station_name
        ).first()
        return device.to_dict() if device else None


def get_rtu_by_id(rtu_id: int) -> dict[str, Any] | None:
    """Get an RTU by its ID."""
    with get_db() as db:
        device = db.query(RTU).filter(RTU.id == rtu_id).first()
        return device.to_dict() if device else None


def create_rtu_device(device: dict[str, Any]) -> int:
    """Create a new RTU device with default slots."""
    defaults = settings.rtu_defaults
    with get_db() as db:
        # Create RTU with ORM model
        slot_count = device.get('slot_count', defaults.SLOT_COUNT)
        new_device = RTU(
            station_name=device['station_name'],
            ip_address=device['ip_address'],
            vendor_id=_format_hex_id(device.get('vendor_id', defaults.VENDOR_ID)),
            device_id=_format_hex_id(device.get('device_id', defaults.DEVICE_ID)),
            slot_count=slot_count,
            state=RtuState.OFFLINE,
            state_since=datetime.now(UTC),
        )
        db.add(new_device)
        db.flush()  # Get the ID

        # Create default empty slots
        for slot_num in range(1, slot_count + 1):
            slot = Slot(
                rtu_id=new_device.id,
                slot_number=slot_num,
                status=SlotStatus.EMPTY,
            )
            db.add(slot)

        db.commit()
        db.refresh(new_device)
        log_audit('system', 'create', 'rtu_device', device['station_name'],
                  f"Created RTU {device['station_name']}")
        return new_device.id


def update_rtu_device(station_name: str, device: dict[str, Any]) -> bool:
    """Update an RTU device."""
    defaults = settings.rtu_defaults
    with get_db() as db:
        existing = db.query(RTU).filter(
            RTU.station_name == station_name
        ).first()
        if not existing:
            return False

        existing.ip_address = device['ip_address']
        existing.vendor_id = _format_hex_id(device.get('vendor_id', defaults.VENDOR_ID))
        existing.device_id = _format_hex_id(device.get('device_id', defaults.DEVICE_ID))

        # Handle slot count changes
        new_slot_count = device.get('slot_count', defaults.SLOT_COUNT)
        if new_slot_count != existing.slot_count:
            _update_slot_count(db, existing, new_slot_count)
            existing.slot_count = new_slot_count

        existing.updated_at = datetime.now(UTC)
        db.commit()
        return True


def update_rtu_state(station_name: str, state: str, error: str | None = None,
                     reason: str | None = None) -> bool:
    """Update RTU state with optional error and reason."""
    with get_db() as db:
        rtu = db.query(RTU).filter(RTU.station_name == station_name).first()
        if not rtu:
            return False
        rtu.update_state(state, error=error, reason=reason)
        db.commit()
        return True


def delete_rtu_device(station_name: str) -> bool:
    """Delete an RTU device (cascade deletes slots, sensors, controls)."""
    with get_db() as db:
        device = db.query(RTU).filter(
            RTU.station_name == station_name
        ).first()
        if not device:
            return False

        # Cascade delete is handled by SQLAlchemy relationships
        db.delete(device)
        db.commit()
        log_audit('system', 'delete', 'rtu_device', station_name,
                  f"Deleted RTU {station_name} with cascade")
        return True


# ============== RTU Sensors Operations ==============

def get_rtu_sensors(rtu_station: str) -> list[dict[str, Any]]:
    """Get all sensors for an RTU."""
    with get_db() as db:
        rtu = db.query(RTU).filter(RTU.station_name == rtu_station).first()
        if not rtu:
            return []
        sensors = db.query(Sensor).filter(
            Sensor.rtu_id == rtu.id
        ).order_by(Sensor.tag).all()
        return [_sensor_to_legacy_dict(s, rtu_station) for s in sensors]


def get_sensor_by_tag(tag: str) -> dict[str, Any] | None:
    """Get a sensor by its unique tag."""
    with get_db() as db:
        sensor = db.query(Sensor).filter(Sensor.tag == tag).first()
        if not sensor:
            return None
        rtu = db.query(RTU).filter(RTU.id == sensor.rtu_id).first()
        return _sensor_to_legacy_dict(sensor, rtu.station_name if rtu else "")


def upsert_rtu_sensor(sensor: dict[str, Any]) -> int:
    """Insert or update an RTU sensor."""
    with get_db() as db:
        rtu = db.query(RTU).filter(
            RTU.station_name == sensor['rtu_station']
        ).first()
        if not rtu:
            return -1

        # Get slot (default to slot 1 if not specified)
        slot_number = sensor.get('slot_number', 1)
        slot = db.query(Slot).filter(
            Slot.rtu_id == rtu.id,
            Slot.slot_number == slot_number
        ).first()
        if not slot:
            return -1

        # Check for existing sensor by tag (unique identifier)
        tag = sensor.get('sensor_id', sensor.get('tag'))
        existing = db.query(Sensor).filter(Sensor.tag == tag).first()

        if existing:
            existing.sensor_type = sensor['sensor_type']
            existing.unit = sensor.get('unit')
            existing.scale_min = sensor.get('scale_min', 0)
            existing.scale_max = sensor.get('scale_max', 100)
            existing.eng_min = sensor.get('eng_min', sensor.get('scale_min', 0))
            existing.eng_max = sensor.get('eng_max', sensor.get('scale_max', 100))
            existing.channel = sensor.get('channel', 0)
            db.commit()
            return existing.id
        else:
            new_sensor = Sensor(
                rtu_id=rtu.id,
                slot_id=slot.id,
                tag=tag,
                channel=sensor.get('channel', 0),
                sensor_type=sensor['sensor_type'],
                unit=sensor.get('unit'),
                scale_min=sensor.get('scale_min', 0),
                scale_max=sensor.get('scale_max', 100),
                eng_min=sensor.get('eng_min', sensor.get('scale_min', 0)),
                eng_max=sensor.get('eng_max', sensor.get('scale_max', 100)),
            )
            db.add(new_sensor)
            db.commit()
            db.refresh(new_sensor)
            return new_sensor.id


def delete_rtu_sensor(rtu_station: str, sensor_id: str) -> bool:
    """Delete an RTU sensor by station name and sensor ID (tag)."""
    with get_db() as db:
        rtu = db.query(RTU).filter(RTU.station_name == rtu_station).first()
        if not rtu:
            return False

        sensor = db.query(Sensor).filter(
            Sensor.rtu_id == rtu.id,
            Sensor.tag == sensor_id
        ).first()
        if not sensor:
            return False

        db.delete(sensor)
        db.commit()
        return True


def clear_rtu_sensors(rtu_station: str) -> int:
    """Clear all sensors for an RTU (before inventory refresh)."""
    with get_db() as db:
        rtu = db.query(RTU).filter(RTU.station_name == rtu_station).first()
        if not rtu:
            return 0
        count = db.query(Sensor).filter(Sensor.rtu_id == rtu.id).delete()
        db.commit()
        return count


# ============== RTU Controls Operations ==============

def get_rtu_controls(rtu_station: str) -> list[dict[str, Any]]:
    """Get all controls for an RTU."""
    with get_db() as db:
        rtu = db.query(RTU).filter(RTU.station_name == rtu_station).first()
        if not rtu:
            return []
        controls = db.query(Control).filter(
            Control.rtu_id == rtu.id
        ).order_by(Control.tag).all()
        return [_control_to_legacy_dict(c, rtu_station) for c in controls]


def get_control_by_tag(tag: str) -> dict[str, Any] | None:
    """Get a control by its unique tag."""
    with get_db() as db:
        control = db.query(Control).filter(Control.tag == tag).first()
        if not control:
            return None
        rtu = db.query(RTU).filter(RTU.id == control.rtu_id).first()
        return _control_to_legacy_dict(control, rtu.station_name if rtu else "")


def upsert_rtu_control(control: dict[str, Any]) -> int:
    """Insert or update an RTU control."""
    with get_db() as db:
        rtu = db.query(RTU).filter(
            RTU.station_name == control['rtu_station']
        ).first()
        if not rtu:
            return -1

        # Get slot (default to slot 1 if not specified)
        slot_number = control.get('slot_number', 1)
        slot = db.query(Slot).filter(
            Slot.rtu_id == rtu.id,
            Slot.slot_number == slot_number
        ).first()
        if not slot:
            return -1

        # Check for existing control by tag (unique identifier)
        tag = control.get('control_id', control.get('tag'))
        existing = db.query(Control).filter(Control.tag == tag).first()

        # Map legacy command_type to control_type
        control_type = control.get('control_type')
        if not control_type and control.get('command_type'):
            control_type = 'discrete' if control['command_type'] == 'on_off' else 'analog'

        if existing:
            existing.control_type = control_type or existing.control_type
            existing.equipment_type = control.get('equipment_type')
            existing.min_value = control.get('range_min', control.get('min_value'))
            existing.max_value = control.get('range_max', control.get('max_value'))
            existing.unit = control.get('unit')
            existing.channel = control.get('channel', 0)
            db.commit()
            return existing.id
        else:
            new_control = Control(
                rtu_id=rtu.id,
                slot_id=slot.id,
                tag=tag,
                channel=control.get('channel', 0),
                control_type=control_type or 'discrete',
                equipment_type=control.get('equipment_type'),
                min_value=control.get('range_min', control.get('min_value')),
                max_value=control.get('range_max', control.get('max_value')),
                unit=control.get('unit'),
            )
            db.add(new_control)
            db.commit()
            db.refresh(new_control)
            return new_control.id


def delete_rtu_control(rtu_station: str, control_id: str) -> bool:
    """Delete an RTU control by station name and control ID (tag)."""
    with get_db() as db:
        rtu = db.query(RTU).filter(RTU.station_name == rtu_station).first()
        if not rtu:
            return False

        control = db.query(Control).filter(
            Control.rtu_id == rtu.id,
            Control.tag == control_id
        ).first()
        if not control:
            return False

        db.delete(control)
        db.commit()
        return True


def clear_rtu_controls(rtu_station: str) -> int:
    """Clear all controls for an RTU (before inventory refresh)."""
    with get_db() as db:
        rtu = db.query(RTU).filter(RTU.station_name == rtu_station).first()
        if not rtu:
            return 0
        count = db.query(Control).filter(Control.rtu_id == rtu.id).delete()
        db.commit()
        return count


# ============== Inventory Operations ==============

def get_rtu_inventory(rtu_station: str) -> dict[str, Any] | None:
    """Get complete inventory for an RTU (sensors + controls)."""
    device = get_rtu_device(rtu_station)
    if not device:
        return None

    return {
        "rtu_station": rtu_station,
        "device": device,
        "sensors": get_rtu_sensors(rtu_station),
        "controls": get_rtu_controls(rtu_station)
    }


# ============== Slot Operations ==============

def get_rtu_slots(rtu_station: str) -> list[dict[str, Any]]:
    """Get all slots for an RTU."""
    with get_db() as db:
        rtu = db.query(RTU).filter(RTU.station_name == rtu_station).first()
        if not rtu:
            return []
        slots = db.query(Slot).filter(
            Slot.rtu_id == rtu.id
        ).order_by(Slot.slot_number).all()
        return [s.to_dict() for s in slots]


def update_slot(rtu_station: str, slot_number: int, **kwargs: Any) -> bool:
    """Update a slot's module information."""
    with get_db() as db:
        rtu = db.query(RTU).filter(RTU.station_name == rtu_station).first()
        if not rtu:
            return False

        slot = db.query(Slot).filter(
            Slot.rtu_id == rtu.id,
            Slot.slot_number == slot_number
        ).first()
        if not slot:
            return False

        for key, value in kwargs.items():
            if hasattr(slot, key):
                setattr(slot, key, value)

        slot.updated_at = datetime.now(UTC)
        db.commit()
        return True


# ============== Helper Functions ==============

def _format_hex_id(value: int | str) -> str:
    """Format vendor/device ID as hex string (e.g., '0x002A')."""
    if isinstance(value, str):
        if value.startswith('0x'):
            return value
        return f"0x{int(value):04X}"
    return f"0x{value:04X}"


def _update_slot_count(db: Any, rtu: RTU, new_count: int) -> None:
    """Add or remove slots to match new count."""
    current_slots = db.query(Slot).filter(Slot.rtu_id == rtu.id).count()

    if new_count > current_slots:
        # Add new slots
        for slot_num in range(current_slots + 1, new_count + 1):
            slot = Slot(
                rtu_id=rtu.id,
                slot_number=slot_num,
                status=SlotStatus.EMPTY,
            )
            db.add(slot)
    elif new_count < current_slots:
        # Remove extra slots (and their sensors/controls via cascade)
        db.query(Slot).filter(
            Slot.rtu_id == rtu.id,
            Slot.slot_number > new_count
        ).delete()


def _sensor_to_legacy_dict(sensor: Sensor, rtu_station: str) -> dict[str, Any]:
    """Convert Sensor model to legacy API format for backward compatibility."""
    return {
        "id": sensor.id,
        "rtu_station": rtu_station,
        "sensor_id": sensor.tag,
        "sensor_type": sensor.sensor_type,
        "name": sensor.tag,
        "unit": sensor.unit,
        "scale_min": sensor.scale_min,
        "scale_max": sensor.scale_max,
        "eng_min": sensor.eng_min,
        "eng_max": sensor.eng_max,
        "channel": sensor.channel,
        "slot_id": sensor.slot_id,
        "created_at": sensor.created_at.isoformat() if sensor.created_at else None,
        "updated_at": sensor.updated_at.isoformat() if sensor.updated_at else None,
    }


def _control_to_legacy_dict(control: Control, rtu_station: str) -> dict[str, Any]:
    """Convert Control model to legacy API format for backward compatibility."""
    return {
        "id": control.id,
        "rtu_station": rtu_station,
        "control_id": control.tag,
        "control_type": control.control_type,
        "name": control.tag,
        "equipment_type": control.equipment_type,
        "command_type": "on_off" if control.control_type == "discrete" else "analog",
        "range_min": control.min_value,
        "range_max": control.max_value,
        "unit": control.unit,
        "channel": control.channel,
        "slot_id": control.slot_id,
        "created_at": control.created_at.isoformat() if control.created_at else None,
        "updated_at": control.updated_at.isoformat() if control.updated_at else None,
    }
