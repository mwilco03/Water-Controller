"""
Water Treatment Controller - Centralized Path Configuration
Copyright (C) 2024-2025
SPDX-License-Identifier: GPL-3.0-or-later

This module provides:
1. Single source of truth for all system paths
2. Startup validation to fail-fast if required paths are missing
3. Ownership and permission verification
4. Clear error messages for operators

Anti-pattern addressed: Hardcoded paths scattered across codebase with no validation.

Usage:
    from app.core.paths import paths, validate_paths

    # Access paths
    db_path = paths.database_file

    # Validate at startup
    issues = validate_paths()
    if issues.has_critical_failures:
        sys.exit(1)
"""

import os
import stat
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class PathSeverity(Enum):
    """Severity levels for path validation issues."""
    CRITICAL = "critical"  # System cannot function
    WARNING = "warning"    # System degraded but operational
    INFO = "info"          # Informational only


@dataclass
class PathIssue:
    """A single path validation issue."""
    path: str
    severity: PathSeverity
    message: str
    operator_action: str  # What the operator should do

    def __str__(self) -> str:
        return f"[{self.severity.value.upper()}] {self.path}: {self.message}"


@dataclass
class ValidationResult:
    """Result of path validation with operator guidance."""
    issues: List[PathIssue] = field(default_factory=list)

    @property
    def has_critical_failures(self) -> bool:
        return any(i.severity == PathSeverity.CRITICAL for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == PathSeverity.WARNING for i in self.issues)

    @property
    def is_healthy(self) -> bool:
        return len(self.issues) == 0

    def log_issues(self) -> None:
        """Log all issues with actionable guidance."""
        for issue in self.issues:
            if issue.severity == PathSeverity.CRITICAL:
                logger.error(
                    f"Path validation FAILED: {issue.path} - {issue.message}. "
                    f"ACTION REQUIRED: {issue.operator_action}"
                )
            elif issue.severity == PathSeverity.WARNING:
                logger.warning(
                    f"Path validation warning: {issue.path} - {issue.message}. "
                    f"RECOMMENDED: {issue.operator_action}"
                )
            else:
                logger.info(f"Path info: {issue.path} - {issue.message}")


class SystemPaths:
    """
    Centralized path configuration with environment variable overrides.

    Environment Variables:
        WTC_INSTALL_DIR: Installation directory (default: /opt/water-controller)
        WTC_CONFIG_DIR: Configuration directory (default: /etc/water-controller)
        WTC_DATA_DIR: Data directory (default: /var/lib/water-controller)
        WTC_LOG_DIR: Log directory (default: /var/log/water-controller)
        WTC_DB_PATH: Database file path (default: <data_dir>/wtc.db)
        WTC_UI_DIST_DIR: UI distribution directory (default: <install_dir>/web/ui/.next)
    """

    def __init__(self):
        # Base directories with environment overrides
        self._install_dir = os.environ.get(
            "WTC_INSTALL_DIR", "/opt/water-controller"
        )
        self._config_dir = os.environ.get(
            "WTC_CONFIG_DIR", "/etc/water-controller"
        )
        self._data_dir = os.environ.get(
            "WTC_DATA_DIR", "/var/lib/water-controller"
        )
        self._log_dir = os.environ.get(
            "WTC_LOG_DIR", "/var/log/water-controller"
        )

    # === Base Directories ===

    @property
    def install_dir(self) -> Path:
        """Main installation directory."""
        return Path(self._install_dir)

    @property
    def config_dir(self) -> Path:
        """Configuration files directory."""
        return Path(self._config_dir)

    @property
    def data_dir(self) -> Path:
        """Persistent data directory (database, backups)."""
        return Path(self._data_dir)

    @property
    def log_dir(self) -> Path:
        """Log files directory."""
        return Path(self._log_dir)

    # === Application Directories ===

    @property
    def venv_dir(self) -> Path:
        """Python virtual environment."""
        return self.install_dir / "venv"

    @property
    def app_dir(self) -> Path:
        """Python application directory."""
        return self.install_dir / "app"

    @property
    def bin_dir(self) -> Path:
        """Compiled binaries directory."""
        return self.install_dir / "bin"

    @property
    def web_dir(self) -> Path:
        """Web assets root directory."""
        return self.install_dir / "web"

    # === UI Paths ===

    @property
    def ui_dir(self) -> Path:
        """UI source directory."""
        return self.web_dir / "ui"

    @property
    def ui_dist_dir(self) -> Path:
        """UI build output directory (Next.js .next folder)."""
        custom = os.environ.get("WTC_UI_DIST_DIR")
        if custom:
            return Path(custom)
        return self.ui_dir / ".next"

    @property
    def ui_static_dir(self) -> Path:
        """UI static assets directory."""
        return self.ui_dist_dir / "static"

    @property
    def ui_server_dir(self) -> Path:
        """UI server-side rendered pages."""
        return self.ui_dist_dir / "server"

    # === Database Paths ===

    @property
    def database_file(self) -> Path:
        """Main SQLite database file."""
        custom = os.environ.get("WTC_DB_PATH")
        if custom:
            return Path(custom)
        return self.data_dir / "wtc.db"

    @property
    def historian_dir(self) -> Path:
        """Historian data directory."""
        return self.data_dir / "historian"

    @property
    def backup_dir(self) -> Path:
        """Backup storage directory."""
        return self.data_dir / "backups"

    # === Configuration Files ===

    @property
    def main_config(self) -> Path:
        """Main controller configuration file."""
        return self.config_dir / "controller.conf"

    @property
    def environment_file(self) -> Path:
        """Environment variables file."""
        return self.config_dir / "environment"

    @property
    def modbus_config(self) -> Path:
        """Modbus gateway configuration."""
        return self.config_dir / "modbus.conf"

    # === IPC Paths ===

    @property
    def run_dir(self) -> Path:
        """Runtime directory (for sockets, PID files)."""
        return Path("/run/water-controller")

    @property
    def shm_name(self) -> str:
        """Shared memory name for IPC."""
        return os.environ.get("WTC_SHM_NAME", "/wtc_shared_memory")

    # === Binary Paths ===

    @property
    def controller_binary(self) -> Path:
        """Main C controller binary."""
        return self.bin_dir / "water_treat_controller"

    @property
    def modbus_binary(self) -> Path:
        """Modbus gateway binary."""
        return self.bin_dir / "modbus_gateway"


# Singleton instance
paths = SystemPaths()


def validate_paths(
    check_ui: bool = True,
    check_database: bool = True,
    check_config: bool = True,
    expected_user: Optional[str] = None,
) -> ValidationResult:
    """
    Validate that all required paths exist with correct permissions.

    This should be called at startup to fail-fast if the system is
    incorrectly installed.

    Args:
        check_ui: Whether to validate UI assets exist
        check_database: Whether to validate database accessibility
        check_config: Whether to validate configuration files
        expected_user: Expected owner of data directories (e.g., 'water-controller')

    Returns:
        ValidationResult with list of issues and helper properties
    """
    result = ValidationResult()

    # === Critical: Base directories must exist ===
    for name, path in [
        ("install_dir", paths.install_dir),
        ("data_dir", paths.data_dir),
    ]:
        if not path.exists():
            result.issues.append(PathIssue(
                path=str(path),
                severity=PathSeverity.CRITICAL,
                message=f"{name} does not exist",
                operator_action=f"Run installation script or create directory: sudo mkdir -p {path}",
            ))
        elif not path.is_dir():
            result.issues.append(PathIssue(
                path=str(path),
                severity=PathSeverity.CRITICAL,
                message=f"{name} exists but is not a directory",
                operator_action=f"Remove file and create directory: sudo rm {path} && sudo mkdir -p {path}",
            ))

    # === Critical: UI assets must exist (if serving UI) ===
    if check_ui:
        if not paths.ui_dist_dir.exists():
            result.issues.append(PathIssue(
                path=str(paths.ui_dist_dir),
                severity=PathSeverity.CRITICAL,
                message="UI build output directory missing - UI will not load",
                operator_action="Build UI: cd /opt/water-controller/web/ui && npm run build",
            ))
        else:
            # Check for essential UI files
            build_manifest = paths.ui_dist_dir / "build-manifest.json"
            if not build_manifest.exists():
                result.issues.append(PathIssue(
                    path=str(build_manifest),
                    severity=PathSeverity.CRITICAL,
                    message="UI build manifest missing - build may be incomplete",
                    operator_action="Rebuild UI: cd /opt/water-controller/web/ui && npm run build",
                ))

            # Check for static chunks
            static_chunks = paths.ui_static_dir / "chunks"
            if paths.ui_static_dir.exists() and not static_chunks.exists():
                result.issues.append(PathIssue(
                    path=str(static_chunks),
                    severity=PathSeverity.WARNING,
                    message="UI static chunks missing - some pages may not load",
                    operator_action="Rebuild UI: cd /opt/water-controller/web/ui && npm run build",
                ))

    # === Warning: Configuration directory ===
    if check_config:
        if not paths.config_dir.exists():
            result.issues.append(PathIssue(
                path=str(paths.config_dir),
                severity=PathSeverity.WARNING,
                message="Configuration directory missing - using defaults",
                operator_action=f"Create config directory: sudo mkdir -p {paths.config_dir}",
            ))
        elif not paths.main_config.exists():
            result.issues.append(PathIssue(
                path=str(paths.main_config),
                severity=PathSeverity.INFO,
                message="Main config file missing - using defaults",
                operator_action="Create config from template or run with defaults",
            ))

    # === Database accessibility ===
    if check_database:
        db_dir = paths.database_file.parent
        if not db_dir.exists():
            result.issues.append(PathIssue(
                path=str(db_dir),
                severity=PathSeverity.CRITICAL,
                message="Database directory missing",
                operator_action=f"Create database directory: sudo mkdir -p {db_dir}",
            ))
        elif paths.database_file.exists():
            # Check if readable
            if not os.access(paths.database_file, os.R_OK):
                result.issues.append(PathIssue(
                    path=str(paths.database_file),
                    severity=PathSeverity.CRITICAL,
                    message="Database file exists but is not readable",
                    operator_action=f"Fix permissions: sudo chmod 644 {paths.database_file}",
                ))
            # Check if writable
            if not os.access(paths.database_file, os.W_OK):
                result.issues.append(PathIssue(
                    path=str(paths.database_file),
                    severity=PathSeverity.CRITICAL,
                    message="Database file exists but is not writable",
                    operator_action=f"Fix permissions: sudo chown {expected_user or 'water-controller'}:{expected_user or 'water-controller'} {paths.database_file}",
                ))

    # === Log directory writability ===
    if paths.log_dir.exists():
        if not os.access(paths.log_dir, os.W_OK):
            result.issues.append(PathIssue(
                path=str(paths.log_dir),
                severity=PathSeverity.WARNING,
                message="Log directory not writable - logs may fail",
                operator_action=f"Fix permissions: sudo chown {expected_user or 'water-controller'} {paths.log_dir}",
            ))

    # === Ownership check ===
    if expected_user and paths.data_dir.exists():
        try:
            data_stat = paths.data_dir.stat()
            import pwd
            try:
                actual_owner = pwd.getpwuid(data_stat.st_uid).pw_name
                if actual_owner != expected_user:
                    result.issues.append(PathIssue(
                        path=str(paths.data_dir),
                        severity=PathSeverity.WARNING,
                        message=f"Data directory owned by '{actual_owner}', expected '{expected_user}'",
                        operator_action=f"Fix ownership: sudo chown -R {expected_user}:{expected_user} {paths.data_dir}",
                    ))
            except KeyError:
                # User ID not found in passwd
                pass
        except (OSError, ImportError):
            pass

    return result


def get_ui_asset_status() -> dict:
    """
    Get detailed UI asset status for health checks.

    Returns dict with:
        - available: bool - whether UI can be served
        - build_time: optional ISO timestamp of last build
        - missing_assets: list of missing critical files
        - message: human-readable status
    """
    status = {
        "available": False,
        "build_time": None,
        "missing_assets": [],
        "message": "Unknown",
    }

    if not paths.ui_dist_dir.exists():
        status["message"] = "UI not built - .next directory missing"
        status["missing_assets"].append(str(paths.ui_dist_dir))
        return status

    # Check build manifest
    build_manifest = paths.ui_dist_dir / "build-manifest.json"
    if build_manifest.exists():
        try:
            mtime = build_manifest.stat().st_mtime
            from datetime import datetime, timezone
            status["build_time"] = datetime.fromtimestamp(
                mtime, tz=timezone.utc
            ).isoformat()
        except OSError:
            pass
    else:
        status["missing_assets"].append("build-manifest.json")

    # Check essential directories
    essential_dirs = [
        paths.ui_dist_dir / "server",
        paths.ui_static_dir,
    ]
    for d in essential_dirs:
        if not d.exists():
            status["missing_assets"].append(str(d.relative_to(paths.ui_dist_dir)))

    if not status["missing_assets"]:
        status["available"] = True
        status["message"] = "UI assets available"
    else:
        status["message"] = f"UI incomplete: missing {', '.join(status['missing_assets'])}"

    return status
