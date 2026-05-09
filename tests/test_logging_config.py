"""Unit tests for the logging configuration module.

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from pathlib import Path

import pytest

from bedrock_iac_agent.logging_config import (
    ConsoleHandlerConfig,
    FileHandlerConfig,
    LoggingConfig,
    RotationConfig,
    logging_config_from_dict,
    setup_logging,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_bedrock_logger() -> logging.Logger:
    """Return the bedrock_iac_agent root logger."""
    return logging.getLogger("bedrock_iac_agent")


def _clear_bedrock_logger() -> None:
    """Remove all handlers from the bedrock_iac_agent logger."""
    logger = _get_bedrock_logger()
    logger.handlers.clear()


# ---------------------------------------------------------------------------
# LoggingConfig defaults
# ---------------------------------------------------------------------------


class TestLoggingConfigDefaults:
    """Verify default values for all config dataclasses."""

    def test_default_level_is_info(self):
        cfg = LoggingConfig()
        assert cfg.level == "INFO"

    def test_console_enabled_by_default(self):
        cfg = LoggingConfig()
        assert cfg.console.enabled is True

    def test_file_disabled_by_default(self):
        cfg = LoggingConfig()
        assert cfg.file.enabled is False

    def test_rotation_enabled_by_default(self):
        cfg = LoggingConfig()
        assert cfg.file.rotation.enabled is True

    def test_rotation_defaults(self):
        rot = RotationConfig()
        assert rot.max_bytes == 10 * 1024 * 1024
        assert rot.backup_count == 5


# ---------------------------------------------------------------------------
# logging_config_from_dict
# ---------------------------------------------------------------------------


class TestLoggingConfigFromDict:
    """Test parsing a raw YAML dict into a LoggingConfig."""

    def test_empty_dict_returns_defaults(self):
        cfg = logging_config_from_dict({})
        assert cfg.level == "INFO"
        assert cfg.console.enabled is True
        assert cfg.file.enabled is False

    def test_non_dict_returns_defaults(self):
        cfg = logging_config_from_dict(None)  # type: ignore[arg-type]
        assert cfg.level == "INFO"

    def test_level_is_uppercased(self):
        cfg = logging_config_from_dict({"level": "debug"})
        assert cfg.level == "DEBUG"

    def test_console_can_be_disabled(self):
        cfg = logging_config_from_dict({"console": {"enabled": False}})
        assert cfg.console.enabled is False

    def test_console_level_override(self):
        cfg = logging_config_from_dict({"console": {"level": "warning"}})
        assert cfg.console.level == "WARNING"

    def test_file_enabled(self):
        cfg = logging_config_from_dict({"file": {"enabled": True, "path": "/tmp/test.log"}})
        assert cfg.file.enabled is True
        assert cfg.file.path == "/tmp/test.log"

    def test_file_level_override(self):
        cfg = logging_config_from_dict({"file": {"level": "debug"}})
        assert cfg.file.level == "DEBUG"

    def test_rotation_settings(self):
        raw = {
            "file": {
                "rotation": {
                    "enabled": True,
                    "max_bytes": 5242880,
                    "backup_count": 3,
                }
            }
        }
        cfg = logging_config_from_dict(raw)
        assert cfg.file.rotation.enabled is True
        assert cfg.file.rotation.max_bytes == 5242880
        assert cfg.file.rotation.backup_count == 3

    def test_rotation_can_be_disabled(self):
        cfg = logging_config_from_dict({"file": {"rotation": {"enabled": False}}})
        assert cfg.file.rotation.enabled is False

    def test_full_config(self):
        raw = {
            "level": "DEBUG",
            "console": {"enabled": True, "level": "INFO"},
            "file": {
                "enabled": True,
                "path": "logs/agent.log",
                "level": "DEBUG",
                "rotation": {"enabled": True, "max_bytes": 1048576, "backup_count": 10},
            },
        }
        cfg = logging_config_from_dict(raw)
        assert cfg.level == "DEBUG"
        assert cfg.console.level == "INFO"
        assert cfg.file.enabled is True
        assert cfg.file.path == "logs/agent.log"
        assert cfg.file.level == "DEBUG"
        assert cfg.file.rotation.max_bytes == 1048576
        assert cfg.file.rotation.backup_count == 10


# ---------------------------------------------------------------------------
# setup_logging — log level
# ---------------------------------------------------------------------------


class TestSetupLoggingLevel:
    """Verify that setup_logging applies the correct log level."""

    def teardown_method(self):
        _clear_bedrock_logger()

    def test_info_level(self):
        setup_logging(LoggingConfig(level="INFO"))
        assert _get_bedrock_logger().level == logging.INFO

    def test_debug_level(self):
        setup_logging(LoggingConfig(level="DEBUG"))
        assert _get_bedrock_logger().level == logging.DEBUG

    def test_warning_level(self):
        setup_logging(LoggingConfig(level="WARNING"))
        assert _get_bedrock_logger().level == logging.WARNING

    def test_error_level(self):
        setup_logging(LoggingConfig(level="ERROR"))
        assert _get_bedrock_logger().level == logging.ERROR

    def test_none_config_uses_info(self):
        setup_logging(None)
        assert _get_bedrock_logger().level == logging.INFO

    def test_unknown_level_falls_back_to_info(self):
        setup_logging(LoggingConfig(level="VERBOSE"))
        assert _get_bedrock_logger().level == logging.INFO


# ---------------------------------------------------------------------------
# setup_logging — console handler
# ---------------------------------------------------------------------------


class TestSetupLoggingConsole:
    """Verify console handler creation and configuration."""

    def teardown_method(self):
        _clear_bedrock_logger()

    def test_console_handler_added_by_default(self):
        setup_logging(LoggingConfig())
        handlers = _get_bedrock_logger().handlers
        stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler)
                           and not isinstance(h, logging.FileHandler)]
        assert len(stream_handlers) == 1

    def test_console_handler_disabled(self):
        cfg = LoggingConfig()
        cfg.console.enabled = False
        setup_logging(cfg)
        handlers = _get_bedrock_logger().handlers
        stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler)
                           and not isinstance(h, logging.FileHandler)]
        assert len(stream_handlers) == 0

    def test_console_handler_uses_json_formatter(self):
        from bedrock_iac_agent.audit_logger import JSONFormatter

        setup_logging(LoggingConfig())
        handlers = _get_bedrock_logger().handlers
        stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler)
                           and not isinstance(h, logging.FileHandler)]
        assert isinstance(stream_handlers[0].formatter, JSONFormatter)

    def test_console_handler_level_override(self):
        cfg = LoggingConfig(level="DEBUG")
        cfg.console.level = "WARNING"
        setup_logging(cfg)
        handlers = _get_bedrock_logger().handlers
        stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler)
                           and not isinstance(h, logging.FileHandler)]
        assert stream_handlers[0].level == logging.WARNING

    def test_repeated_calls_do_not_duplicate_handlers(self):
        setup_logging(LoggingConfig())
        setup_logging(LoggingConfig())
        handlers = _get_bedrock_logger().handlers
        stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler)
                           and not isinstance(h, logging.FileHandler)]
        assert len(stream_handlers) == 1


# ---------------------------------------------------------------------------
# setup_logging — file handler
# ---------------------------------------------------------------------------


class TestSetupLoggingFile:
    """Verify file handler creation, rotation, and directory creation."""

    def teardown_method(self):
        _clear_bedrock_logger()

    def test_file_handler_not_added_when_disabled(self):
        setup_logging(LoggingConfig())  # file.enabled defaults to False
        handlers = _get_bedrock_logger().handlers
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0

    def test_file_handler_added_when_enabled(self, tmp_path):
        cfg = LoggingConfig()
        cfg.file.enabled = True
        cfg.file.path = str(tmp_path / "test.log")
        setup_logging(cfg)
        handlers = _get_bedrock_logger().handlers
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_rotating_file_handler_used_when_rotation_enabled(self, tmp_path):
        cfg = LoggingConfig()
        cfg.file.enabled = True
        cfg.file.path = str(tmp_path / "test.log")
        cfg.file.rotation.enabled = True
        setup_logging(cfg)
        handlers = _get_bedrock_logger().handlers
        rotating = [h for h in handlers
                    if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(rotating) == 1

    def test_plain_file_handler_used_when_rotation_disabled(self, tmp_path):
        cfg = LoggingConfig()
        cfg.file.enabled = True
        cfg.file.path = str(tmp_path / "test.log")
        cfg.file.rotation.enabled = False
        setup_logging(cfg)
        handlers = _get_bedrock_logger().handlers
        # Should be a plain FileHandler, NOT a RotatingFileHandler
        plain = [h for h in handlers
                 if type(h) is logging.FileHandler]
        assert len(plain) == 1

    def test_rotating_handler_respects_max_bytes(self, tmp_path):
        cfg = LoggingConfig()
        cfg.file.enabled = True
        cfg.file.path = str(tmp_path / "test.log")
        cfg.file.rotation.max_bytes = 1024
        cfg.file.rotation.backup_count = 3
        setup_logging(cfg)
        handlers = _get_bedrock_logger().handlers
        rotating = [h for h in handlers
                    if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert rotating[0].maxBytes == 1024
        assert rotating[0].backupCount == 3

    def test_parent_directories_created_automatically(self, tmp_path):
        nested_path = tmp_path / "a" / "b" / "c" / "agent.log"
        cfg = LoggingConfig()
        cfg.file.enabled = True
        cfg.file.path = str(nested_path)
        setup_logging(cfg)
        assert nested_path.parent.exists()

    def test_file_handler_uses_json_formatter(self, tmp_path):
        from bedrock_iac_agent.audit_logger import JSONFormatter

        cfg = LoggingConfig()
        cfg.file.enabled = True
        cfg.file.path = str(tmp_path / "test.log")
        setup_logging(cfg)
        handlers = _get_bedrock_logger().handlers
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert isinstance(file_handlers[0].formatter, JSONFormatter)

    def test_file_handler_level_override(self, tmp_path):
        cfg = LoggingConfig(level="INFO")
        cfg.file.enabled = True
        cfg.file.path = str(tmp_path / "test.log")
        cfg.file.level = "DEBUG"
        setup_logging(cfg)
        handlers = _get_bedrock_logger().handlers
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert file_handlers[0].level == logging.DEBUG

    def test_log_messages_written_to_file(self, tmp_path):
        log_file = tmp_path / "output.log"
        cfg = LoggingConfig(level="DEBUG")
        cfg.file.enabled = True
        cfg.file.path = str(log_file)
        cfg.file.rotation.enabled = False
        setup_logging(cfg)

        test_logger = logging.getLogger("bedrock_iac_agent.test_write")
        test_logger.info("hello from test")

        content = log_file.read_text(encoding="utf-8").strip()
        assert content, "Log file should not be empty"
        log_data = json.loads(content.split("\n")[-1])
        assert "hello from test" in log_data["message"]

    def test_log_messages_are_valid_json_in_file(self, tmp_path):
        log_file = tmp_path / "output.log"
        cfg = LoggingConfig(level="DEBUG")
        cfg.file.enabled = True
        cfg.file.path = str(log_file)
        cfg.file.rotation.enabled = False
        setup_logging(cfg)

        test_logger = logging.getLogger("bedrock_iac_agent.test_json")
        test_logger.info("message one")
        test_logger.warning("message two")

        lines = [l for l in log_file.read_text(encoding="utf-8").strip().split("\n") if l.strip()]
        # At least the two messages we logged (setup_logging may also emit a DEBUG line)
        assert len(lines) >= 2
        # All lines must be valid JSON with required fields
        for line in lines:
            data = json.loads(line)
            assert "timestamp" in data
            assert "level" in data
            assert "message" in data
        # The last two lines should be our messages
        messages = [json.loads(l)["message"] for l in lines[-2:]]
        assert "message one" in messages
        assert "message two" in messages


# ---------------------------------------------------------------------------
# setup_logging — no propagation
# ---------------------------------------------------------------------------


class TestSetupLoggingPropagation:
    """Verify the logger does not propagate to the root Python logger."""

    def teardown_method(self):
        _clear_bedrock_logger()

    def test_propagation_disabled(self):
        setup_logging(LoggingConfig())
        assert _get_bedrock_logger().propagate is False


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


class TestEnvVarOverrides:
    """Verify that environment variables override config values."""

    def teardown_method(self):
        _clear_bedrock_logger()
        for var in ("LOG_LEVEL", "LOG_FILE", "LOG_FILE_ENABLED"):
            os.environ.pop(var, None)

    def test_log_level_env_var(self):
        os.environ["LOG_LEVEL"] = "DEBUG"
        setup_logging(LoggingConfig(level="INFO"))
        assert _get_bedrock_logger().level == logging.DEBUG

    def test_log_file_env_var_enables_file_logging(self, tmp_path):
        log_file = str(tmp_path / "env.log")
        os.environ["LOG_FILE"] = log_file
        cfg = LoggingConfig()
        cfg.file.rotation.enabled = False
        setup_logging(cfg)
        handlers = _get_bedrock_logger().handlers
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_log_file_enabled_false_disables_file_logging(self, tmp_path):
        os.environ["LOG_FILE_ENABLED"] = "false"
        cfg = LoggingConfig()
        cfg.file.enabled = True
        cfg.file.path = str(tmp_path / "should_not_create.log")
        setup_logging(cfg)
        handlers = _get_bedrock_logger().handlers
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0

    def test_log_file_enabled_true_enables_file_logging(self, tmp_path):
        log_file = str(tmp_path / "enabled.log")
        os.environ["LOG_FILE_ENABLED"] = "true"
        os.environ["LOG_FILE"] = log_file
        cfg = LoggingConfig()
        cfg.file.rotation.enabled = False
        setup_logging(cfg)
        handlers = _get_bedrock_logger().handlers
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1


# ---------------------------------------------------------------------------
# ConfigurationManager integration
# ---------------------------------------------------------------------------


class TestConfigManagerIntegration:
    """Verify that ConfigurationManager.to_logging_config() works correctly."""

    def test_to_logging_config_returns_defaults_when_no_logging_section(self, tmp_path):
        from bedrock_iac_agent.config_manager import ConfigurationManager

        # Write a config.yaml without a logging section
        config_file = tmp_path / "config.yaml"
        config_file.write_text("bedrock:\n  region: us-east-1\n")

        mgr = ConfigurationManager(config_path=str(config_file))
        log_cfg = mgr.to_logging_config()

        assert log_cfg.level == "INFO"
        assert log_cfg.console.enabled is True
        assert log_cfg.file.enabled is False

    def test_to_logging_config_reads_level_from_yaml(self, tmp_path):
        from bedrock_iac_agent.config_manager import ConfigurationManager

        config_file = tmp_path / "config.yaml"
        config_file.write_text("logging:\n  level: DEBUG\n")

        mgr = ConfigurationManager(config_path=str(config_file))
        log_cfg = mgr.to_logging_config()

        assert log_cfg.level == "DEBUG"

    def test_to_logging_config_reads_file_settings_from_yaml(self, tmp_path):
        from bedrock_iac_agent.config_manager import ConfigurationManager

        log_path = str(tmp_path / "agent.log")
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            f"logging:\n"
            f"  file:\n"
            f"    enabled: true\n"
            f"    path: {log_path}\n"
            f"    rotation:\n"
            f"      max_bytes: 2097152\n"
            f"      backup_count: 3\n"
        )

        mgr = ConfigurationManager(config_path=str(config_file))
        log_cfg = mgr.to_logging_config()

        assert log_cfg.file.enabled is True
        assert log_cfg.file.path == log_path
        assert log_cfg.file.rotation.max_bytes == 2097152
        assert log_cfg.file.rotation.backup_count == 3


# ---------------------------------------------------------------------------
# AuditLogger.add_rotating_file_handler
# ---------------------------------------------------------------------------


class TestAuditLoggerRotatingHandler:
    """Verify the new add_rotating_file_handler method on AuditLogger."""

    def test_rotating_handler_added(self, tmp_path):
        from bedrock_iac_agent.audit_logger import AuditLogger

        log_file = str(tmp_path / "audit.log")
        al = AuditLogger(logger_name="test_rotating_audit")
        al.add_rotating_file_handler(log_file, max_bytes=1024, backup_count=2)

        rotating = [
            h for h in al.logger.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(rotating) == 1
        assert rotating[0].maxBytes == 1024
        assert rotating[0].backupCount == 2

    def test_rotating_handler_creates_parent_dirs(self, tmp_path):
        from bedrock_iac_agent.audit_logger import AuditLogger

        nested = tmp_path / "x" / "y" / "audit.log"
        al = AuditLogger(logger_name="test_rotating_dirs")
        al.add_rotating_file_handler(str(nested))
        assert nested.parent.exists()

    def test_rotating_handler_writes_json(self, tmp_path):
        from datetime import datetime
        from bedrock_iac_agent.audit_logger import AuditLogger

        log_file = tmp_path / "audit.log"
        al = AuditLogger(logger_name="test_rotating_json")
        al.add_rotating_file_handler(str(log_file))

        al.log_request("user@example.com", "Create S3 bucket", datetime.now(), "req-001")

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        # The rotating handler writes one line; the console handler may also write
        json_lines = [l for l in lines if l.strip()]
        assert len(json_lines) >= 1
        data = json.loads(json_lines[-1])
        assert data["event_type"] == "user_request"
        assert data["user_id"] == "user@example.com"
