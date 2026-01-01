#!/usr/bin/env python3
"""
Configuration File Validator

Validates configuration files (JSON) against their corresponding schemas.
This is a runtime validation tool to ensure config files are correct
before deployment.

Usage:
    python scripts/validate_config.py                        # Validate all configs
    python scripts/validate_config.py docker/config/water-controller.json
    python scripts/validate_config.py --strict               # Fail on warnings

Exit codes:
    0 - All configurations valid
    1 - Validation errors found
    2 - Warnings found (with --strict)
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:
    print("ERROR: jsonschema not installed. Run: pip install jsonschema", file=sys.stderr)
    sys.exit(1)

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_DIR = PROJECT_ROOT / "schemas" / "config"

# Config file to schema mapping
CONFIG_SCHEMA_MAP = {
    "water-controller.json": "controller.schema.yaml",
    "web-config.json": "web.schema.yaml",
    "modbus-config.json": "modbus.schema.yaml",
    "alarms.json": "alarms.schema.yaml",
}

# Default config file locations
DEFAULT_CONFIG_PATHS = [
    PROJECT_ROOT / "docker" / "config" / "water-controller.json",
    PROJECT_ROOT / "config" / "water-controller.json",
]


def load_json_config(path: Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Load a JSON configuration file."""
    errors = []

    if not path.exists():
        return None, [f"File not found: {path}"]

    try:
        with open(path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        return None, [f"JSON parse error at line {e.lineno}: {e.msg}"]
    except Exception as e:
        return None, [f"Failed to read file: {e}"]

    if not isinstance(config, dict):
        return None, ["Configuration must be a JSON object"]

    return config, errors


def load_yaml_schema(path: Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Load a YAML schema file."""
    errors = []

    if not path.exists():
        return None, [f"Schema not found: {path}"]

    try:
        with open(path, "r") as f:
            schema = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return None, [f"YAML parse error: {e}"]
    except Exception as e:
        return None, [f"Failed to read schema: {e}"]

    return schema, errors


def find_schema_for_config(config_path: Path) -> Optional[Path]:
    """Find the corresponding schema file for a config file."""
    config_name = config_path.name

    # Check explicit mapping
    if config_name in CONFIG_SCHEMA_MAP:
        return SCHEMA_DIR / CONFIG_SCHEMA_MAP[config_name]

    # Try to infer schema name
    # water-controller.json -> controller.schema.yaml
    base_name = config_path.stem  # water-controller
    possible_names = [
        f"{base_name}.schema.yaml",
        f"{base_name.replace('-', '_')}.schema.yaml",
        f"{base_name.split('-')[-1]}.schema.yaml",  # controller from water-controller
    ]

    for name in possible_names:
        schema_path = SCHEMA_DIR / name
        if schema_path.exists():
            return schema_path

    return None


def validate_config(
    config: Dict[str, Any],
    schema: Dict[str, Any],
    config_path: str
) -> Tuple[List[str], List[str]]:
    """Validate a configuration against a schema."""
    errors = []
    warnings = []

    try:
        validator = Draft202012Validator(schema)
        validation_errors = list(validator.iter_errors(config))

        for error in validation_errors:
            path = ".".join(str(p) for p in error.absolute_path) or "(root)"
            errors.append(f"{path}: {error.message}")
    except jsonschema.exceptions.SchemaError as e:
        errors.append(f"Invalid schema: {e.message}")

    # Additional validation checks
    warnings.extend(check_deprecated_fields(config, schema))
    warnings.extend(check_security_settings(config, config_path))

    return errors, warnings


def check_deprecated_fields(config: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    """Check for deprecated fields in configuration."""
    warnings = []

    # Check schema properties for x-deprecated
    if "properties" in schema:
        for field, prop in schema["properties"].items():
            if isinstance(prop, dict) and prop.get("x-deprecated"):
                if field in config:
                    msg = prop.get("x-deprecated-message", "Field is deprecated")
                    warnings.append(f"DEPRECATED: '{field}' - {msg}")

    return warnings


def check_security_settings(config: Dict[str, Any], config_path: str) -> List[str]:
    """Check for potential security issues in configuration."""
    warnings = []

    # Check for default passwords
    password_fields = ["password", "secret", "key", "token"]
    def check_passwords(obj, path=""):
        for key, value in obj.items() if isinstance(obj, dict) else []:
            current_path = f"{path}.{key}" if path else key
            if any(pf in key.lower() for pf in password_fields):
                if isinstance(value, str):
                    if value in ["admin", "password", "secret", "default", "changeme", ""]:
                        warnings.append(f"SECURITY: '{current_path}' appears to be a default/weak password")
            if isinstance(value, dict):
                check_passwords(value, current_path)

    check_passwords(config)

    # Check for plaintext credentials
    if "database" in config:
        db = config["database"]
        if isinstance(db, dict) and "password" in db:
            if not db.get("password", "").startswith("${"):  # Not env var reference
                warnings.append("SECURITY: Database password should use environment variable reference")

    return warnings


def find_config_files(paths: List[str]) -> List[Path]:
    """Find configuration files to validate."""
    config_files = []

    if not paths:
        # Use default paths
        for path in DEFAULT_CONFIG_PATHS:
            if path.exists():
                config_files.append(path)
    else:
        for path_str in paths:
            path = Path(path_str)
            if path.is_file():
                config_files.append(path)
            elif path.is_dir():
                config_files.extend(path.glob("*.json"))
            else:
                print(f"WARNING: Path not found: {path}", file=sys.stderr)

    return config_files


def main():
    parser = argparse.ArgumentParser(description="Validate configuration files")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Configuration files or directories to validate"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on warnings"
    )
    parser.add_argument(
        "--schema",
        help="Override schema file to use"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    args = parser.parse_args()

    config_files = find_config_files(args.paths)

    if not config_files:
        print("No configuration files found to validate.", file=sys.stderr)
        print("Specify files or ensure default configs exist at:")
        for p in DEFAULT_CONFIG_PATHS:
            print(f"  {p}")
        sys.exit(1)

    print(f"Validating {len(config_files)} configuration file(s)...\n")

    total_errors = 0
    total_warnings = 0

    for config_path in config_files:
        print(f"  {config_path.name}... ", end="")

        # Load config
        config, load_errors = load_json_config(config_path)
        if load_errors:
            print("FAILED")
            for err in load_errors:
                print(f"    ERROR: {err}")
            total_errors += len(load_errors)
            continue

        # Find schema
        if args.schema:
            schema_path = Path(args.schema)
        else:
            schema_path = find_schema_for_config(config_path)

        if not schema_path:
            print("SKIPPED (no schema)")
            if args.verbose:
                print(f"    No schema found for {config_path.name}")
            continue

        # Load schema
        schema, schema_errors = load_yaml_schema(schema_path)
        if schema_errors:
            print("FAILED")
            for err in schema_errors:
                print(f"    ERROR: {err}")
            total_errors += len(schema_errors)
            continue

        # Validate
        errors, warnings = validate_config(config, schema, str(config_path))

        if errors:
            print("FAILED")
            for err in errors:
                print(f"    ERROR: {err}")
            total_errors += len(errors)
        elif warnings:
            if args.strict:
                print("FAILED (warnings in strict mode)")
            else:
                print("OK (with warnings)")
            for warn in warnings:
                print(f"    {warn}")
            total_warnings += len(warnings)
        else:
            print("OK")
            if args.verbose:
                print(f"    Validated against {schema_path.name}")

    print()

    # Summary
    if total_errors:
        print(f"FAILED: {total_errors} error(s)")
        sys.exit(1)
    elif total_warnings and args.strict:
        print(f"FAILED: {total_warnings} warning(s) in strict mode")
        sys.exit(2)
    else:
        print("SUCCESS: All configurations valid")
        if total_warnings:
            print(f"  ({total_warnings} warning(s))")
        sys.exit(0)


if __name__ == "__main__":
    main()
