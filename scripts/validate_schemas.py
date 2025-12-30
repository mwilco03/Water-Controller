#!/usr/bin/env python3
"""
Validate JSON Schema YAML files and check for drift.

This script validates all schemas and optionally checks if generated files
are in sync with the schemas.

Usage:
    python scripts/validate_schemas.py              # Validate only
    python scripts/validate_schemas.py --check      # Validate and check drift
    python scripts/validate_schemas.py --regenerate # Regenerate all artifacts

Exit codes:
    0 - All schemas valid, no drift (or regenerated successfully)
    1 - Schema validation errors
    2 - Generated files out of sync (drift detected)
"""

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:
    print("WARNING: jsonschema not installed. Schema validation will be limited.", file=sys.stderr)
    jsonschema = None


SCHEMA_DIR = Path(__file__).parent.parent / "schemas" / "config"
SCRIPTS_DIR = Path(__file__).parent

GENERATED_FILES = [
    "docs/generated/CONFIGURATION.md",
    "src/generated/config_types.h",
    "src/generated/config_defaults.h",
    "web/api/models/generated/config_models.py",
    "web/api/models/generated/__init__.py",
]


def load_schema(path: Path) -> Tuple[Dict[str, Any], List[str]]:
    """Load a YAML schema file and return (schema, errors)."""
    errors = []

    try:
        with open(path, "r") as f:
            schema = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return {}, [f"YAML parse error: {e}"]
    except Exception as e:
        return {}, [f"Failed to read file: {e}"]

    if not isinstance(schema, dict):
        return {}, ["Schema must be an object"]

    return schema, errors


def validate_schema_structure(schema: Dict[str, Any], path: Path) -> List[str]:
    """Validate schema has required fields and proper structure."""
    errors = []

    # Check required top-level fields
    if "$schema" not in schema:
        errors.append("Missing $schema field")

    if "$id" not in schema:
        errors.append("Missing $id field")

    if "title" not in schema:
        errors.append("Missing title field")

    if "type" not in schema:
        errors.append("Missing type field")
    elif schema["type"] != "object":
        errors.append("Root type must be 'object'")

    return errors


def validate_with_jsonschema(schema: Dict[str, Any]) -> List[str]:
    """Validate schema against JSON Schema Draft 2020-12."""
    if jsonschema is None:
        return []

    errors = []

    try:
        # Check if it's a valid JSON Schema
        Draft202012Validator.check_schema(schema)
    except jsonschema.exceptions.SchemaError as e:
        errors.append(f"Invalid JSON Schema: {e.message}")

    return errors


def validate_properties(props: Dict[str, Any], path: str = "") -> List[str]:
    """Validate property definitions."""
    errors = []

    for name, prop in props.items():
        prop_path = f"{path}.{name}" if path else name

        if not isinstance(prop, dict):
            errors.append(f"{prop_path}: Property must be an object")
            continue

        if "type" not in prop and "enum" not in prop and "$ref" not in prop:
            errors.append(f"{prop_path}: Missing type, enum, or $ref")

        # Check that defaults match types
        if "default" in prop and "type" in prop:
            default = prop["default"]
            prop_type = prop["type"]

            if prop_type == "boolean" and not isinstance(default, bool):
                errors.append(f"{prop_path}: Default must be boolean")
            elif prop_type == "integer" and not isinstance(default, int):
                errors.append(f"{prop_path}: Default must be integer")
            elif prop_type == "number" and not isinstance(default, (int, float)):
                errors.append(f"{prop_path}: Default must be number")
            elif prop_type == "string" and not isinstance(default, str):
                errors.append(f"{prop_path}: Default must be string")
            elif prop_type == "array" and not isinstance(default, list):
                errors.append(f"{prop_path}: Default must be array")

        # Check enum values
        if "enum" in prop:
            if not isinstance(prop["enum"], list):
                errors.append(f"{prop_path}: enum must be an array")
            elif len(prop["enum"]) == 0:
                errors.append(f"{prop_path}: enum must not be empty")

        # Check min/max constraints
        if "minimum" in prop and "maximum" in prop:
            if prop["minimum"] > prop["maximum"]:
                errors.append(f"{prop_path}: minimum > maximum")

        # Recursively check nested objects
        if prop.get("type") == "object" and "properties" in prop:
            errors.extend(validate_properties(prop["properties"], prop_path))

    return errors


def validate_x_extensions(props: Dict[str, Any], path: str = "") -> List[str]:
    """Validate custom x-* extensions."""
    errors = []
    warnings = []

    for name, prop in props.items():
        prop_path = f"{path}.{name}" if path else name

        if not isinstance(prop, dict):
            continue

        # Check x-env-var format
        if "x-env-var" in prop:
            env_var = prop["x-env-var"]
            if not env_var.startswith("WTC_") and not env_var.startswith("WT_"):
                warnings.append(f"{prop_path}: x-env-var '{env_var}' should start with WTC_ or WT_")

        # Check x-unit is provided for numeric types with units
        if prop.get("type") in ("integer", "number"):
            name_lower = name.lower()
            if any(u in name_lower for u in ("_ms", "_sec", "_min", "_hour", "timeout", "interval", "delay")):
                if "x-unit" not in prop:
                    warnings.append(f"{prop_path}: Numeric field with time-related name should have x-unit")

        # Recursively check nested objects
        if prop.get("type") == "object" and "properties" in prop:
            nested_errors = validate_x_extensions(prop["properties"], prop_path)
            errors.extend(nested_errors)

    # Warnings are returned as errors with "WARNING:" prefix
    for w in warnings:
        errors.append(f"WARNING: {w}")

    return errors


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    if not path.exists():
        return ""

    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_drift() -> List[str]:
    """Check if generated files are in sync with schemas."""
    errors = []

    root = Path(__file__).parent.parent

    # Store current hashes
    current_hashes = {}
    for rel_path in GENERATED_FILES:
        full_path = root / rel_path
        current_hashes[rel_path] = compute_file_hash(full_path)

    # Run generators
    generators = [
        "generate_docs.py",
        "generate_c_types.py",
        "generate_pydantic.py",
    ]

    for gen in generators:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / gen)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            errors.append(f"Generator {gen} failed: {result.stderr}")
            return errors

    # Compare hashes
    for rel_path in GENERATED_FILES:
        full_path = root / rel_path
        new_hash = compute_file_hash(full_path)

        if new_hash != current_hashes[rel_path]:
            if current_hashes[rel_path] == "":
                errors.append(f"DRIFT: {rel_path} is missing and needs to be generated")
            else:
                errors.append(f"DRIFT: {rel_path} is out of sync with schemas")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate JSON Schema files")
    parser.add_argument("--check", action="store_true", help="Check for drift in generated files")
    parser.add_argument("--regenerate", action="store_true", help="Regenerate all artifacts")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Find all schema files
    schema_files = sorted(SCHEMA_DIR.glob("*.schema.yaml"))

    if not schema_files:
        print(f"ERROR: No schema files found in {SCHEMA_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Validating {len(schema_files)} schema files...\n")

    total_errors = []
    total_warnings = []

    for sf in schema_files:
        print(f"  {sf.name}...", end=" ")

        schema, load_errors = load_schema(sf)
        if load_errors:
            print("FAILED")
            for err in load_errors:
                print(f"    ERROR: {err}")
            total_errors.extend(load_errors)
            continue

        errors = []
        errors.extend(validate_schema_structure(schema, sf))
        errors.extend(validate_with_jsonschema(schema))

        if "properties" in schema:
            errors.extend(validate_properties(schema["properties"]))
            errors.extend(validate_x_extensions(schema["properties"]))

        # Separate warnings from errors
        file_errors = [e for e in errors if not e.startswith("WARNING:")]
        file_warnings = [e.replace("WARNING: ", "") for e in errors if e.startswith("WARNING:")]

        if file_errors:
            print("FAILED")
            for err in file_errors:
                print(f"    ERROR: {err}")
            total_errors.extend(file_errors)
        elif file_warnings and args.verbose:
            print("OK (with warnings)")
            for warn in file_warnings:
                print(f"    WARNING: {warn}")
        else:
            print("OK")

        total_warnings.extend(file_warnings)

    print()

    # Check for drift if requested
    if args.check and not total_errors:
        print("Checking for drift in generated files...")
        drift_errors = check_drift()

        if drift_errors:
            print()
            for err in drift_errors:
                print(f"  {err}")
            print()
            print("To fix drift, run: python scripts/validate_schemas.py --regenerate")
            sys.exit(2)
        else:
            print("  All generated files are in sync.\n")

    # Regenerate if requested
    if args.regenerate:
        print("Regenerating all artifacts...")
        generators = [
            ("generate_docs.py", "Documentation"),
            ("generate_c_types.py", "C headers"),
            ("generate_pydantic.py", "Pydantic models"),
        ]

        for gen, desc in generators:
            print(f"  Generating {desc}...")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / gen)],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"    FAILED: {result.stderr}")
                total_errors.append(f"Generator {gen} failed")
            else:
                if args.verbose:
                    print(result.stdout)

        print()

    # Summary
    if total_errors:
        print(f"FAILED: {len(total_errors)} error(s)")
        sys.exit(1)
    else:
        print(f"SUCCESS: All schemas valid")
        if total_warnings:
            print(f"  ({len(total_warnings)} warning(s))")
        sys.exit(0)


if __name__ == "__main__":
    main()
