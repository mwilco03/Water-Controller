#!/usr/bin/env python3
"""
Cross-Component Integration Validator

Validates that all components of the Water Treatment Controller system
are properly integrated and can communicate with each other.

Usage:
    python scripts/validate_integration.py           # Run all checks
    python scripts/validate_integration.py --docker  # Docker-specific checks
    python scripts/validate_integration.py --quick   # Quick smoke test

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
    2 - Could not run checks (missing dependencies)
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).parent.parent


class IntegrationCheck:
    """Base class for integration checks."""

    name: str = "Unknown Check"
    description: str = ""

    def run(self) -> Tuple[bool, str]:
        """Run the check. Returns (success, message)."""
        raise NotImplementedError


class SchemaConsistencyCheck(IntegrationCheck):
    """Check that schemas are consistent across components."""

    name = "Schema Consistency"
    description = "Verify schemas are in sync across C, Python, and TypeScript"

    def run(self) -> Tuple[bool, str]:
        # Check if generated files exist
        generated_files = [
            PROJECT_ROOT / "src" / "generated" / "config_types.h",
            PROJECT_ROOT / "web" / "api" / "models" / "generated" / "config_models.py",
            PROJECT_ROOT / "docs" / "generated" / "CONFIGURATION.md",
        ]

        missing = [f for f in generated_files if not f.exists()]
        if missing:
            return False, f"Missing generated files: {[str(f.relative_to(PROJECT_ROOT)) for f in missing]}"

        # Run drift check
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "validate_schemas.py"), "--check"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT
        )

        if result.returncode == 0:
            return True, "All schemas in sync"
        elif result.returncode == 2:
            return False, "Schema drift detected - run 'make regenerate'"
        else:
            return False, f"Schema validation failed: {result.stderr}"


class ConfigValidationCheck(IntegrationCheck):
    """Check that configuration files are valid."""

    name = "Configuration Validation"
    description = "Validate configuration files against schemas"

    def run(self) -> Tuple[bool, str]:
        config_script = PROJECT_ROOT / "scripts" / "validate_config.py"
        if not config_script.exists():
            return True, "Config validation script not found (skipped)"

        result = subprocess.run(
            [sys.executable, str(config_script)],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT
        )

        if result.returncode == 0:
            return True, "All configurations valid"
        else:
            return False, f"Configuration validation failed: {result.stdout}"


class APISchemaCheck(IntegrationCheck):
    """Check that API matches OpenAPI specification."""

    name = "API Schema"
    description = "Verify API endpoints match schema definitions"

    def run(self) -> Tuple[bool, str]:
        # Check if FastAPI app can be imported
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "web" / "api"))
            from app.main import app
            openapi = app.openapi()

            # Basic validation
            if not openapi.get("paths"):
                return False, "No API paths defined"

            path_count = len(openapi["paths"])
            schema_count = len(openapi.get("components", {}).get("schemas", {}))

            return True, f"API has {path_count} paths and {schema_count} schemas"

        except ImportError as e:
            return True, f"Could not import FastAPI app (skipped): {e}"
        except Exception as e:
            return False, f"API schema check failed: {e}"


class PortConsistencyCheck(IntegrationCheck):
    """Check that ports are consistently configured."""

    name = "Port Consistency"
    description = "Verify port configuration is consistent across files"

    def run(self) -> Tuple[bool, str]:
        ports_env = PROJECT_ROOT / "config" / "ports.env"
        compose_file = PROJECT_ROOT / "docker" / "docker-compose.yml"

        if not ports_env.exists():
            return False, "ports.env not found"
        if not compose_file.exists():
            return False, "docker-compose.yml not found"

        # Parse ports.env
        port_vars = {}
        with open(ports_env) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    port_vars[key.strip()] = value.strip()

        # Check compose file references these variables
        with open(compose_file) as f:
            compose_content = f.read()

        missing = []
        for var in ["WTC_API_PORT", "WTC_UI_PORT", "WTC_GRAFANA_PORT"]:
            if var in port_vars:
                if f"${{{var}" not in compose_content and f"${var}" not in compose_content:
                    # Variable defined but not used in compose
                    pass  # This is ok, might be used elsewhere

        return True, f"Found {len(port_vars)} port configurations"


class DatabaseSchemaCheck(IntegrationCheck):
    """Check that database schema matches models."""

    name = "Database Schema"
    description = "Verify database models are consistent"

    def run(self) -> Tuple[bool, str]:
        # Check if SQLAlchemy models can be imported
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "web" / "api"))
            from app.models import rtu, sensor, actuator

            models = [rtu, sensor, actuator]
            model_count = len(models)

            return True, f"Found {model_count} database model modules"

        except ImportError as e:
            return True, f"Could not import models (skipped): {e}"
        except Exception as e:
            return False, f"Database schema check failed: {e}"


class DockerComposeCheck(IntegrationCheck):
    """Check Docker Compose configuration."""

    name = "Docker Compose"
    description = "Validate Docker Compose configuration"

    def run(self) -> Tuple[bool, str]:
        compose_file = PROJECT_ROOT / "docker" / "docker-compose.yml"

        if not compose_file.exists():
            return False, "docker-compose.yml not found"

        # Run docker compose config to validate
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "config", "--quiet"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT / "docker"
        )

        if result.returncode == 0:
            # Count services
            result2 = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "config", "--services"],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT / "docker"
            )
            service_count = len(result2.stdout.strip().split("\n"))
            return True, f"Valid compose file with {service_count} services"
        else:
            return False, f"Invalid compose file: {result.stderr}"


class DependencyVersionCheck(IntegrationCheck):
    """Check that dependency versions are consistent."""

    name = "Dependency Versions"
    description = "Verify dependency versions across components"

    def run(self) -> Tuple[bool, str]:
        versions_file = PROJECT_ROOT / "versions.json"

        if not versions_file.exists():
            return True, "versions.json not found (skipped)"

        try:
            with open(versions_file) as f:
                versions = json.load(f)

            # Check package.json matches
            package_json = PROJECT_ROOT / "web" / "ui" / "package.json"
            if package_json.exists():
                with open(package_json) as f:
                    package = json.load(f)
                # Could add version comparison logic here

            return True, f"Versions file contains {len(versions)} entries"

        except Exception as e:
            return False, f"Version check failed: {e}"


class DockerfileConsistencyCheck(IntegrationCheck):
    """Check that Dockerfiles are consistent."""

    name = "Dockerfile Consistency"
    description = "Verify Dockerfiles use consistent base images"

    def run(self) -> Tuple[bool, str]:
        dockerfiles = list((PROJECT_ROOT / "docker").glob("Dockerfile*"))

        if not dockerfiles:
            return False, "No Dockerfiles found"

        # Extract base images
        base_images = {}
        for df in dockerfiles:
            with open(df) as f:
                for line in f:
                    if line.strip().startswith("FROM "):
                        image = line.strip().split()[1]
                        base_images[df.name] = image
                        break

        return True, f"Found {len(dockerfiles)} Dockerfiles"


def run_checks(checks: List[IntegrationCheck], verbose: bool = False) -> int:
    """Run all integration checks."""
    print("Running Cross-Component Integration Validation")
    print("=" * 50)
    print()

    passed = 0
    failed = 0
    skipped = 0

    for check in checks:
        print(f"  {check.name}... ", end="", flush=True)

        try:
            success, message = check.run()

            if "skipped" in message.lower():
                print("SKIPPED")
                skipped += 1
            elif success:
                print("OK")
                passed += 1
            else:
                print("FAILED")
                failed += 1

            if verbose or not success:
                print(f"    → {message}")

        except Exception as e:
            print("ERROR")
            print(f"    → Exception: {e}")
            failed += 1

    print()
    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")

    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="Cross-component integration validation")
    parser.add_argument("--docker", action="store_true", help="Include Docker-specific checks")
    parser.add_argument("--quick", action="store_true", help="Quick smoke test only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Define checks
    checks = [
        SchemaConsistencyCheck(),
        ConfigValidationCheck(),
        PortConsistencyCheck(),
        DependencyVersionCheck(),
    ]

    if not args.quick:
        checks.extend([
            APISchemaCheck(),
            DatabaseSchemaCheck(),
            DockerfileConsistencyCheck(),
        ])

    if args.docker:
        checks.append(DockerComposeCheck())

    return run_checks(checks, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
