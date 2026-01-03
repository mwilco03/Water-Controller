"""
Water Treatment Controller - DictSerializableMixin Tests
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Tests for the DictSerializableMixin used across all models.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.models.rtu import RTU, RtuState, Sensor, Slot, SlotStatus


class TestDictSerializableMixin:
    """Tests for DictSerializableMixin.to_dict() method."""

    def test_to_dict_basic(self, db_session: Session, sample_rtu: RTU):
        """Test basic to_dict() serialization."""
        result = sample_rtu.to_dict()

        assert isinstance(result, dict)
        assert result["station_name"] == "test-rtu-1"
        assert result["ip_address"] == "192.168.1.10"
        assert result["slot_count"] == 8
        assert "id" in result

    def test_to_dict_datetime_serialization(self, db_session: Session, sample_rtu: RTU):
        """Test datetime fields are serialized to ISO format."""
        result = sample_rtu.to_dict()

        # state_since should be ISO format string
        assert isinstance(result["state_since"], str)
        # Should be parseable as ISO datetime
        datetime.fromisoformat(result["state_since"])

    def test_to_dict_exclude(self, db_session: Session, sample_rtu: RTU):
        """Test exclude parameter filters out columns."""
        result = sample_rtu.to_dict(exclude=["ip_address", "vendor_id"])

        assert "station_name" in result
        assert "ip_address" not in result
        assert "vendor_id" not in result

    def test_to_dict_include(self, db_session: Session, sample_rtu: RTU):
        """Test include parameter limits to specific columns."""
        result = sample_rtu.to_dict(include=["id", "station_name"])

        assert "id" in result
        assert "station_name" in result
        assert "ip_address" not in result
        assert "slot_count" not in result

    def test_to_dict_null_values(self, db_session: Session):
        """Test null values are serialized as None."""
        rtu = RTU(
            station_name="null-test",
            ip_address="192.168.1.99",
            vendor_id="0x0000",
            device_id="0x0000",
            slot_count=8,
            state=RtuState.OFFLINE,
            state_since=datetime.now(UTC),
            firmware_version=None,  # Explicitly null
        )
        db_session.add(rtu)
        db_session.commit()

        result = rtu.to_dict()

        assert result["firmware_version"] is None

    def test_to_dict_slot_model(self, db_session: Session, sample_rtu: RTU):
        """Test to_dict works on Slot model."""
        slot = db_session.query(Slot).filter(
            Slot.rtu_id == sample_rtu.id,
            Slot.slot_number == 1
        ).first()

        result = slot.to_dict()

        assert result["slot_number"] == 1
        assert result["status"] == SlotStatus.EMPTY.value
        assert result["rtu_id"] == sample_rtu.id

    def test_to_dict_sensor_model(self, db_session: Session, sample_sensor: Sensor):
        """Test to_dict works on Sensor model."""
        result = sample_sensor.to_dict()

        assert result["tag"] == "TK-101-LVL"
        assert result["sensor_type"] == "level"
        assert result["unit"] == "ft"
        assert result["scale_min"] == 0.0
        assert result["scale_max"] == 32767.0
        assert result["eng_min"] == 0.0
        assert result["eng_max"] == 20.0


class TestMixinEdgeCases:
    """Edge case tests for the mixin."""

    def test_to_dict_empty_exclude(self, db_session: Session, sample_rtu: RTU):
        """Test empty exclude list returns all columns."""
        result_no_param = sample_rtu.to_dict()
        result_empty = sample_rtu.to_dict(exclude=[])

        assert result_no_param == result_empty

    def test_to_dict_combined_include_exclude(self, db_session: Session, sample_rtu: RTU):
        """Test when both include and exclude are provided."""
        # Include takes precedence - only include fields are considered,
        # then exclude filters those
        result = sample_rtu.to_dict(
            include=["id", "station_name", "ip_address"],
            exclude=["ip_address"]
        )

        assert "id" in result
        assert "station_name" in result
        assert "ip_address" not in result
        assert "slot_count" not in result

    def test_to_dict_enum_serialization(self, db_session: Session, sample_rtu: RTU):
        """Test enum values are serialized correctly."""
        result = sample_rtu.to_dict()

        # RtuState enum should be serialized as its value
        assert result["state"] == RtuState.OFFLINE.value
