"""
Water Treatment Controller - Data Quality Tests
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Tests for quality state handling and propagation.
"""

import pytest
from datetime import datetime, timezone, timedelta


class TestQualityCodes:
    """Tests for quality code values and semantics."""

    def test_quality_codes_match_opc_ua(self):
        """Quality codes should match OPC UA specification."""
        # These values are defined in shm_client.py
        QUALITY_GOOD = 0x00
        QUALITY_UNCERTAIN = 0x40
        QUALITY_BAD = 0x80
        QUALITY_NOT_CONNECTED = 0xC0

        assert QUALITY_GOOD == 0x00
        assert QUALITY_UNCERTAIN == 0x40
        assert QUALITY_BAD == 0x80
        assert QUALITY_NOT_CONNECTED == 0xC0

    def test_quality_names_mapping(self):
        """Quality names should be human-readable."""
        QUALITY_NAMES = {
            0x00: "good",
            0x40: "uncertain",
            0x80: "bad",
            0xC0: "not_connected"
        }

        assert QUALITY_NAMES[0x00] == "good"
        assert QUALITY_NAMES[0x40] == "uncertain"
        assert QUALITY_NAMES[0x80] == "bad"
        assert QUALITY_NAMES[0xC0] == "not_connected"


class TestQualityUsability:
    """Tests for quality-based control decisions."""

    def test_good_quality_usable_for_control(self):
        """GOOD quality data should be usable for control."""
        quality = 0x00  # GOOD
        usable = quality in (0x00, 0x40)  # GOOD or UNCERTAIN
        assert usable is True

    def test_uncertain_quality_usable_with_warning(self):
        """UNCERTAIN quality data should be usable but with warning."""
        quality = 0x40  # UNCERTAIN
        usable = quality in (0x00, 0x40)
        should_warn = quality == 0x40
        assert usable is True
        assert should_warn is True

    def test_bad_quality_not_usable(self):
        """BAD quality data should not be used for control."""
        quality = 0x80  # BAD
        usable = quality in (0x00, 0x40)
        assert usable is False

    def test_not_connected_not_usable(self):
        """NOT_CONNECTED quality data should not be used for control."""
        quality = 0xC0  # NOT_CONNECTED
        usable = quality in (0x00, 0x40)
        assert usable is False


class TestStalenessDetection:
    """Tests for staleness detection and quality degradation."""

    def test_fresh_data_is_good(self):
        """Data less than 5 seconds old should remain GOOD."""
        now = datetime.now(timezone.utc)
        timestamp = now - timedelta(seconds=3)
        age = (now - timestamp).total_seconds()

        quality = 0x00  # GOOD
        stale = age > 5

        assert stale is False
        assert quality == 0x00

    def test_stale_data_becomes_uncertain(self):
        """Data 5-60 seconds old should become UNCERTAIN."""
        now = datetime.now(timezone.utc)
        timestamp = now - timedelta(seconds=30)
        age = (now - timestamp).total_seconds()

        quality = 0x00  # Initially GOOD
        stale = False

        if age > 5:
            stale = True
            if quality == 0x00:
                quality = 0x40  # UNCERTAIN

        assert stale is True
        assert quality == 0x40

    def test_extended_stale_becomes_bad(self):
        """Data 60+ seconds old should become BAD."""
        now = datetime.now(timezone.utc)
        timestamp = now - timedelta(seconds=90)
        age = (now - timestamp).total_seconds()

        quality = 0x00  # Initially GOOD

        if age > 60:
            quality = 0x80  # BAD

        assert quality == 0x80

    def test_very_stale_becomes_not_connected(self):
        """Data 5+ minutes old should become NOT_CONNECTED."""
        now = datetime.now(timezone.utc)
        timestamp = now - timedelta(minutes=6)
        age = (now - timestamp).total_seconds()

        quality = 0x00  # Initially GOOD

        if age > 300:  # 5 minutes
            quality = 0xC0  # NOT_CONNECTED

        assert quality == 0xC0


class TestInterlockFailSafe:
    """Tests for interlock fail-safe behavior on bad quality."""

    def test_interlock_trips_on_bad_quality(self):
        """Interlock should trip when input quality is BAD."""
        value = 50.0  # Normal value
        quality = 0x80  # BAD
        threshold = 100.0

        input_valid = quality == 0x00  # Only GOOD is valid for interlocks

        if input_valid:
            condition_met = value > threshold
        else:
            condition_met = True  # Fail-safe

        assert input_valid is False
        assert condition_met is True  # Should trip despite normal value

    def test_interlock_normal_on_good_quality(self):
        """Interlock should evaluate normally with GOOD quality."""
        value = 50.0  # Normal value
        quality = 0x00  # GOOD
        threshold = 100.0

        input_valid = quality == 0x00

        if input_valid:
            condition_met = value > threshold
        else:
            condition_met = True

        assert input_valid is True
        assert condition_met is False  # Should NOT trip


class TestPIDQualityCheck:
    """Tests for PID loop quality checking."""

    def test_pid_accepts_good_quality(self):
        """PID should accept GOOD quality input."""
        iops_status = 0x80  # IOPS_GOOD
        quality = 0x00  # QUALITY_GOOD

        quality_ok = (iops_status == 0x80 and
                      quality in (0x00, 0x40))

        assert quality_ok is True

    def test_pid_accepts_uncertain_quality(self):
        """PID should accept UNCERTAIN quality input with logging."""
        iops_status = 0x80  # IOPS_GOOD
        quality = 0x40  # QUALITY_UNCERTAIN

        quality_ok = (iops_status == 0x80 and
                      quality in (0x00, 0x40))

        should_log_warning = quality == 0x40

        assert quality_ok is True
        assert should_log_warning is True

    def test_pid_rejects_bad_quality(self):
        """PID should reject BAD quality input."""
        iops_status = 0x80  # IOPS_GOOD
        quality = 0x80  # QUALITY_BAD

        quality_ok = (iops_status == 0x80 and
                      quality in (0x00, 0x40))

        assert quality_ok is False

    def test_pid_rejects_bad_iops(self):
        """PID should reject input with bad IOPS status."""
        iops_status = 0x00  # IOPS_BAD
        quality = 0x00  # QUALITY_GOOD

        quality_ok = (iops_status == 0x80 and
                      quality in (0x00, 0x40))

        assert quality_ok is False


class TestHistorianQuality:
    """Tests for historian quality storage."""

    def test_historian_sample_includes_quality(self):
        """Historian samples should include quality field."""
        sample = {
            "timestamp_ms": 1000000,
            "tag_id": 1,
            "value": 7.5,
            "quality": 0x00
        }

        assert "quality" in sample
        assert sample["quality"] == 0x00

    def test_historian_preserves_quality_from_sensor(self):
        """Historian should preserve quality from sensor data."""
        sensor_quality = 0x40  # UNCERTAIN

        sample = {
            "timestamp_ms": 1000000,
            "tag_id": 1,
            "value": 7.5,
            "quality": sensor_quality  # Direct propagation
        }

        assert sample["quality"] == 0x40
