"""
Water Treatment Controller - DictSerializableMixin Tests
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Unit tests for the DictSerializableMixin class.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import DictSerializableMixin


# Create a test-specific base with the mixin
TestBase = declarative_base(cls=DictSerializableMixin)


class SampleModel(TestBase):
    """Sample model for testing DictSerializableMixin."""

    __tablename__ = "sample_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    value = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class CustomSerializeModel(TestBase):
    """Model with custom field serialization."""

    __tablename__ = "custom_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    json_data = Column(Text, nullable=True)  # Stores JSON as string

    def _serialize_field(self, key: str, value):
        """Override to handle JSON field."""
        if key == "json_data" and value is not None:
            import json
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return {}
        return super()._serialize_field(key, value)


@pytest.fixture(scope="function")
def db_session() -> Session:
    """Create a fresh database session for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestBase.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        TestBase.metadata.drop_all(bind=engine)


class TestDictSerializableMixinBasics:
    """Test basic to_dict() functionality."""

    def test_to_dict_returns_all_columns(self, db_session):
        """to_dict() should return all column values."""
        model = SampleModel(name="test", value=42.5, description="A test model")
        db_session.add(model)
        db_session.commit()
        db_session.refresh(model)

        result = model.to_dict()

        assert result["id"] == model.id
        assert result["name"] == "test"
        assert result["value"] == 42.5
        assert result["description"] == "A test model"
        assert "created_at" in result

    def test_to_dict_handles_none_values(self, db_session):
        """to_dict() should handle None values gracefully."""
        model = SampleModel(name="test", value=None, description=None)
        db_session.add(model)
        db_session.commit()

        result = model.to_dict()

        assert result["name"] == "test"
        assert result["value"] is None
        assert result["description"] is None

    def test_to_dict_serializes_datetime_to_iso(self, db_session):
        """to_dict() should serialize datetime to ISO format string."""
        model = SampleModel(name="test")
        db_session.add(model)
        db_session.commit()
        db_session.refresh(model)

        result = model.to_dict()

        assert isinstance(result["created_at"], str)
        # Should be ISO format
        datetime.fromisoformat(result["created_at"])  # Should not raise


class TestDictSerializableMixinFiltering:
    """Test include/exclude filtering."""

    def test_to_dict_with_include(self, db_session):
        """to_dict(include=[...]) should only include specified columns."""
        model = SampleModel(name="test", value=42.5, description="desc")
        db_session.add(model)
        db_session.commit()
        db_session.refresh(model)

        result = model.to_dict(include=["id", "name"])

        assert set(result.keys()) == {"id", "name"}
        assert result["name"] == "test"

    def test_to_dict_with_exclude(self, db_session):
        """to_dict(exclude=[...]) should exclude specified columns."""
        model = SampleModel(name="test", value=42.5, description="desc")
        db_session.add(model)
        db_session.commit()
        db_session.refresh(model)

        result = model.to_dict(exclude=["description", "created_at"])

        assert "description" not in result
        assert "created_at" not in result
        assert result["name"] == "test"
        assert result["value"] == 42.5

    def test_to_dict_include_takes_precedence(self, db_session):
        """When both include and exclude are provided, include takes precedence."""
        model = SampleModel(name="test", value=42.5)
        db_session.add(model)
        db_session.commit()
        db_session.refresh(model)

        result = model.to_dict(include=["id", "name", "value"], exclude=["value"])

        # value should be excluded even though it's in include
        assert "value" not in result
        assert set(result.keys()) == {"id", "name"}


class TestDictSerializableMixinCustom:
    """Test custom _serialize_field() override."""

    def test_custom_serialize_field(self, db_session):
        """Custom _serialize_field() should be called for each field."""
        import json

        model = CustomSerializeModel(json_data=json.dumps({"key": "value"}))
        db_session.add(model)
        db_session.commit()
        db_session.refresh(model)

        result = model.to_dict()

        # Should be deserialized from JSON string to dict
        assert isinstance(result["json_data"], dict)
        assert result["json_data"] == {"key": "value"}

    def test_custom_serialize_field_handles_invalid_json(self, db_session):
        """Custom _serialize_field() should handle invalid JSON gracefully."""
        model = CustomSerializeModel(json_data="not valid json")
        db_session.add(model)
        db_session.commit()
        db_session.refresh(model)

        result = model.to_dict()

        # Should return empty dict for invalid JSON
        assert result["json_data"] == {}

    def test_custom_serialize_field_handles_none(self, db_session):
        """Custom _serialize_field() should handle None values."""
        model = CustomSerializeModel(json_data=None)
        db_session.add(model)
        db_session.commit()
        db_session.refresh(model)

        result = model.to_dict()

        assert result["json_data"] is None


class TestDictSerializableMixinEdgeCases:
    """Test edge cases and error handling."""

    def test_to_dict_empty_include_list(self, db_session):
        """to_dict(include=[]) should return empty dict."""
        model = SampleModel(name="test")
        db_session.add(model)
        db_session.commit()

        result = model.to_dict(include=[])

        assert result == {}

    def test_to_dict_nonexistent_include_column(self, db_session):
        """to_dict() should ignore nonexistent columns in include."""
        model = SampleModel(name="test")
        db_session.add(model)
        db_session.commit()

        result = model.to_dict(include=["nonexistent", "name"])

        assert result == {"name": "test"}

    def test_to_dict_nonexistent_exclude_column(self, db_session):
        """to_dict() should ignore nonexistent columns in exclude."""
        model = SampleModel(name="test")
        db_session.add(model)
        db_session.commit()
        db_session.refresh(model)

        # Should not raise an error
        result = model.to_dict(exclude=["nonexistent"])

        assert "name" in result
