"""Logging configuration for the Bedrock IaC Agent.

Provides a single ``setup_logging()`` entry point that configures the Python
logging system according to settings loaded from ``config.yaml`` (or
environment variables).  All application loggers inherit from the root
``bedrock_iac_agent`` logger, so calling this function once at startup is
sufficient to apply the desired level, handlers, and rotation policy across
the entire package.

Supported configuration (``logging`` section of ``config.yaml``):

.. code-block:: yaml

    logging:
      level: INFO                  # DEBUG | INFO | WARNING | ERROR | CRITICAL
      console:
        enabled: true
        level: INFO                # optional per-handler override
      file:
        enabled: false
        path: logs/bedrock-iac-agent.log
        level: DEBUG               # optional per-handler override
        rotation:
          enabled: true
          max_bytes: 10485760      # 10 MB per file
          backup_count: 5          # keep 5 rotated files

Environment variable overrides:
    LOG_LEVEL          → logging.level
    LOG_FILE           → logging.file.path
    LOG_FILE_ENABLED   → logging.file.enabled  (true/false)

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .audit_logger import JSONFormatter

# ---------------------------------------------------------------------------
# Typed configuration dataclasses
# ---------------------------------------------------------------------------

_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_DEFAULT_BACKUP_COUNT = 5


@dataclass
class RotationConfig:
    """Log rotation settings for the file handler."""

    enabled: bool = True
    max_bytes: int = _DEFAULT_MAX_BYTES
    backup_count: int = _DEFAULT_BACKUP_COUNT


@dataclass
class ConsoleHandlerConfig:
    """Console (stderr/stdout) handler settings."""

    enabled: bool = True
    level: Optional[str] = None  # None → inherit from root logging level


@dataclass
class FileHandlerConfig:
    """File handler settings."""

    enabled: bool = False
    path: str = "logs/bedrock-iac-agent.log"
    level: Optional[str] = None  # None → inherit from root logging level
    rotation: RotationConfig = field(default_factory=RotationConfig)


@dataclass
class LoggingConfig:
    """Top-level logging configuration."""

    level: str = "INFO"
    console: ConsoleHandlerConfig = field(default_factory=ConsoleHandlerConfig)
    file: FileHandlerConfig = field(default_factory=FileHandlerConfig)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def setup_logging(config: Optional[LoggingConfig] = None) -> None:
    """Configure the ``bedrock_iac_agent`` logger hierarchy.

    This function should be called **once** at application startup (e.g. from
    the CLI entry point).  It is idempotent — calling it multiple times with
    the same configuration is safe; existing handlers are replaced rather than
    duplicated.

    Args:
        config: A :class:`LoggingConfig` instance.  When ``None``, a default
            configuration is used (INFO level, console output only).

    Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
    """
    if config is None:
        config = LoggingConfig()

    # Apply environment variable overrides
    config = _apply_env_overrides(config)

    root_logger = logging.getLogger("bedrock_iac_agent")

    # Resolve numeric level
    numeric_level = _resolve_level(config.level)
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates on repeated calls
    root_logger.handlers.clear()

    # Prevent propagation to the Python root logger (avoids double-printing)
    root_logger.propagate = False

    # --- Console handler ---
    if config.console.enabled:
        console_handler = _build_console_handler(config.console, numeric_level)
        root_logger.addHandler(console_handler)

    # --- File handler (with optional rotation) ---
    if config.file.enabled:
        file_handler = _build_file_handler(config.file, numeric_level)
        root_logger.addHandler(file_handler)

    logging.getLogger(__name__).debug(
        "Logging configured: level=%s, console=%s, file=%s (path=%s)",
        config.level,
        config.console.enabled,
        config.file.enabled,
        config.file.path if config.file.enabled else "n/a",
    )


def logging_config_from_dict(raw: dict) -> LoggingConfig:
    """Build a :class:`LoggingConfig` from a raw YAML dictionary.

    This is the bridge between :class:`~bedrock_iac_agent.config_manager.ConfigurationManager`
    and the logging subsystem.

    Args:
        raw: The ``logging`` sub-dictionary from the parsed ``config.yaml``.

    Returns:
        A fully populated :class:`LoggingConfig` instance.
    """
    cfg = LoggingConfig()

    if not isinstance(raw, dict):
        return cfg

    if "level" in raw:
        cfg.level = str(raw["level"]).upper()

    # Console section
    console_raw = raw.get("console", {}) or {}
    if isinstance(console_raw, dict):
        if "enabled" in console_raw:
            cfg.console.enabled = bool(console_raw["enabled"])
        if "level" in console_raw:
            cfg.console.level = str(console_raw["level"]).upper()

    # File section
    file_raw = raw.get("file", {}) or {}
    if isinstance(file_raw, dict):
        if "enabled" in file_raw:
            cfg.file.enabled = bool(file_raw["enabled"])
        if "path" in file_raw:
            cfg.file.path = str(file_raw["path"])
        if "level" in file_raw:
            cfg.file.level = str(file_raw["level"]).upper()

        # Rotation sub-section
        rotation_raw = file_raw.get("rotation", {}) or {}
        if isinstance(rotation_raw, dict):
            if "enabled" in rotation_raw:
                cfg.file.rotation.enabled = bool(rotation_raw["enabled"])
            if "max_bytes" in rotation_raw:
                cfg.file.rotation.max_bytes = int(rotation_raw["max_bytes"])
            if "backup_count" in rotation_raw:
                cfg.file.rotation.backup_count = int(rotation_raw["backup_count"])

    return cfg


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_level(level_str: str) -> int:
    """Convert a level name string to a numeric logging level.

    Falls back to ``logging.INFO`` for unrecognised strings.
    """
    numeric = getattr(logging, level_str.upper(), None)
    if not isinstance(numeric, int):
        logging.warning("Unknown log level %r — defaulting to INFO.", level_str)
        return logging.INFO
    return numeric


def _apply_env_overrides(config: LoggingConfig) -> LoggingConfig:
    """Apply environment variable overrides to a :class:`LoggingConfig`.

    Supported variables:
    - ``LOG_LEVEL``        → ``config.level``
    - ``LOG_FILE``         → ``config.file.path`` (also enables file logging)
    - ``LOG_FILE_ENABLED`` → ``config.file.enabled`` (``"true"`` / ``"false"``)
    """
    log_level = os.environ.get("LOG_LEVEL")
    if log_level:
        config.level = log_level.upper()

    log_file = os.environ.get("LOG_FILE")
    if log_file:
        config.file.path = log_file
        config.file.enabled = True

    log_file_enabled = os.environ.get("LOG_FILE_ENABLED")
    if log_file_enabled is not None:
        config.file.enabled = log_file_enabled.lower() in ("1", "true", "yes")

    return config


def _build_console_handler(
    cfg: ConsoleHandlerConfig,
    root_level: int,
) -> logging.StreamHandler:
    """Create and configure a console (StreamHandler) with JSON formatting."""
    handler = logging.StreamHandler()
    handler_level = _resolve_level(cfg.level) if cfg.level else root_level
    handler.setLevel(handler_level)
    handler.setFormatter(JSONFormatter())
    return handler


def _build_file_handler(
    cfg: FileHandlerConfig,
    root_level: int,
) -> logging.Handler:
    """Create and configure a file handler, with rotation when enabled.

    Creates parent directories automatically if they do not exist.

    Returns:
        A :class:`~logging.handlers.RotatingFileHandler` when rotation is
        enabled, otherwise a plain :class:`~logging.FileHandler`.
    """
    log_path = Path(cfg.path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler_level = _resolve_level(cfg.level) if cfg.level else root_level

    if cfg.rotation.enabled:
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),
            maxBytes=cfg.rotation.max_bytes,
            backupCount=cfg.rotation.backup_count,
            encoding="utf-8",
        )
    else:
        handler = logging.FileHandler(str(log_path), encoding="utf-8")

    handler.setLevel(handler_level)
    handler.setFormatter(JSONFormatter())
    return handler
