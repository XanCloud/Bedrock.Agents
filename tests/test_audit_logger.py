"""Unit tests for the AuditLogger component."""

import json
import logging
from datetime import datetime
from io import StringIO

import pytest

from bedrock_iac_agent.audit_logger import AuditLogger, JSONFormatter
from bedrock_iac_agent.models import (
    Environment,
    ResourceType,
    StructuredRequest,
)


@pytest.fixture
def audit_logger():
    """Create an AuditLogger instance for testing."""
    logger = AuditLogger(logger_name="test_audit_logger")
    return logger


@pytest.fixture
def log_capture():
    """Capture log output for testing."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(JSONFormatter())
    return log_stream, handler


@pytest.fixture
def sample_structured_request():
    """Create a sample StructuredRequest for testing."""
    return StructuredRequest(
        resource_type=ResourceType.S3_BUCKET,
        parameters={"bucket_name": "test-bucket", "versioning": True},
        environment=Environment.DEVELOPMENT,
        confidence=0.95,
        user_justification="Need storage for application logs",
        request_id="req-12345",
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
    )


class TestJSONFormatter:
    """Tests for the JSONFormatter class."""

    def test_format_basic_log_record(self):
        """Test that basic log records are formatted as valid JSON."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        assert "timestamp" in log_data
        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "test"
        assert log_data["message"] == "Test message"

    def test_format_with_extra_fields(self):
        """Test that extra fields are included in JSON output."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.event_type = "test_event"
        record.user_id = "user123"
        record.request_id = "req-456"

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        assert log_data["event_type"] == "test_event"
        assert log_data["user_id"] == "user123"
        assert log_data["request_id"] == "req-456"

    def test_format_timestamp_is_iso8601(self):
        """Test that timestamp is in ISO 8601 format with Z suffix."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        # Check that timestamp ends with Z and can be parsed
        assert log_data["timestamp"].endswith("Z")
        datetime.fromisoformat(log_data["timestamp"].rstrip("Z"))


class TestAuditLogger:
    """Tests for the AuditLogger class."""

    def test_logger_initialization(self, audit_logger):
        """Test that logger is properly initialized."""
        assert audit_logger.logger is not None
        assert audit_logger.logger.name == "test_audit_logger"
        assert audit_logger.logger.level == logging.INFO
        assert len(audit_logger.logger.handlers) > 0

    def test_log_request(self, audit_logger, log_capture):
        """Test logging of user requests."""
        log_stream, handler = log_capture
        audit_logger.logger.addHandler(handler)

        user_id = "developer@company.com"
        request = "Create an S3 bucket for storing logs in development"
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        request_id = "req-12345"

        audit_logger.log_request(user_id, request, timestamp, request_id)

        log_output = log_stream.getvalue()
        log_data = json.loads(log_output.strip().split("\n")[-1])

        assert log_data["event_type"] == "user_request"
        assert log_data["user_id"] == user_id
        assert log_data["request_id"] == request_id
        assert log_data["status"] == "received"
        assert "Create an S3 bucket" in log_data["message"]

    def test_log_request_generates_id_if_not_provided(self, audit_logger, log_capture):
        """Test that log_request generates a request_id if not provided."""
        log_stream, handler = log_capture
        audit_logger.logger.addHandler(handler)

        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        audit_logger.log_request("user123", "Test request", timestamp)

        log_output = log_stream.getvalue()
        log_data = json.loads(log_output.strip().split("\n")[-1])

        assert "request_id" in log_data
        assert log_data["request_id"].startswith("req-")

    def test_log_configuration(self, audit_logger, log_capture, sample_structured_request):
        """Test logging of generated configurations."""
        log_stream, handler = log_capture
        audit_logger.logger.addHandler(handler)

        tfvars_content = """
bucket_name = "test-bucket"
versioning = true
"""

        audit_logger.log_configuration(sample_structured_request, tfvars_content)

        log_output = log_stream.getvalue()
        log_data = json.loads(log_output.strip().split("\n")[-1])

        assert log_data["event_type"] == "configuration_generated"
        assert log_data["request_id"] == "req-12345"
        assert log_data["resource_type"] == "s3_bucket"
        assert log_data["environment"] == "dev"
        assert log_data["status"] == "generated"
        assert "context" in log_data
        assert log_data["context"]["confidence"] == 0.95
        assert "bucket_name" in log_data["context"]["parameters"]

    def test_log_pull_request(self, audit_logger, log_capture):
        """Test logging of Pull Request creation."""
        log_stream, handler = log_capture
        audit_logger.logger.addHandler(handler)

        pr_url = "https://github.com/org/repo/pull/123"
        request_id = "req-12345"

        audit_logger.log_pull_request(
            pr_url,
            request_id,
            ResourceType.S3_BUCKET,
            Environment.DEVELOPMENT,
        )

        log_output = log_stream.getvalue()
        log_data = json.loads(log_output.strip().split("\n")[-1])

        assert log_data["event_type"] == "pull_request_created"
        assert log_data["request_id"] == request_id
        assert log_data["pr_url"] == pr_url
        assert log_data["resource_type"] == "s3_bucket"
        assert log_data["environment"] == "dev"
        assert log_data["status"] == "success"

    def test_log_pull_request_without_optional_fields(self, audit_logger, log_capture):
        """Test logging PR creation without optional resource_type and environment."""
        log_stream, handler = log_capture
        audit_logger.logger.addHandler(handler)

        pr_url = "https://github.com/org/repo/pull/123"
        request_id = "req-12345"

        audit_logger.log_pull_request(pr_url, request_id)

        log_output = log_stream.getvalue()
        log_data = json.loads(log_output.strip().split("\n")[-1])

        assert log_data["event_type"] == "pull_request_created"
        assert log_data["pr_url"] == pr_url
        assert "resource_type" not in log_data
        assert "environment" not in log_data

    def test_log_model_usage(self, audit_logger, log_capture):
        """Test logging of Bedrock model usage."""
        log_stream, handler = log_capture
        audit_logger.logger.addHandler(handler)

        model_name = "anthropic.claude-3-haiku-20240307-v1:0"
        tokens_consumed = 450
        cost = 0.0023
        request_id = "req-12345"

        audit_logger.log_model_usage(model_name, tokens_consumed, cost, request_id)

        log_output = log_stream.getvalue()
        log_data = json.loads(log_output.strip().split("\n")[-1])

        assert log_data["event_type"] == "model_usage"
        assert log_data["model_used"] == model_name
        assert log_data["tokens_consumed"] == tokens_consumed
        assert log_data["cost"] == cost
        assert log_data["request_id"] == request_id
        assert log_data["status"] == "completed"

    def test_log_model_usage_without_request_id(self, audit_logger, log_capture):
        """Test logging model usage without request_id."""
        log_stream, handler = log_capture
        audit_logger.logger.addHandler(handler)

        audit_logger.log_model_usage("test-model", 100, 0.001)

        log_output = log_stream.getvalue()
        log_data = json.loads(log_output.strip().split("\n")[-1])

        assert log_data["event_type"] == "model_usage"
        assert "request_id" not in log_data

    def test_log_error_with_stack_trace(self, audit_logger, log_capture):
        """Test that error logging includes stack traces."""
        log_stream, handler = log_capture
        audit_logger.logger.addHandler(handler)

        try:
            raise ValueError("Test error message")
        except ValueError as e:
            context = {
                "user_id": "user123",
                "request_id": "req-456",
                "resource_type": "s3_bucket",
                "operation": "generate_tfvars",
            }
            audit_logger.log_error(e, context, error_code="VALIDATION_ERROR")

        log_output = log_stream.getvalue()
        log_data = json.loads(log_output.strip().split("\n")[-1])

        assert log_data["event_type"] == "error"
        assert log_data["error_code"] == "VALIDATION_ERROR"
        assert log_data["status"] == "error"
        assert log_data["user_id"] == "user123"
        assert log_data["request_id"] == "req-456"
        assert log_data["resource_type"] == "s3_bucket"
        assert "stack_trace" in log_data
        assert "ValueError" in log_data["stack_trace"]
        assert "Test error message" in log_data["stack_trace"]
        assert log_data["context"]["operation"] == "generate_tfvars"

    def test_log_error_uses_exception_type_as_default_code(self, audit_logger, log_capture):
        """Test that error code defaults to exception type name."""
        log_stream, handler = log_capture
        audit_logger.logger.addHandler(handler)

        try:
            raise ConnectionError("Network failure")
        except ConnectionError as e:
            audit_logger.log_error(e, {})

        log_output = log_stream.getvalue()
        log_data = json.loads(log_output.strip().split("\n")[-1])

        assert log_data["error_code"] == "ConnectionError"

    def test_set_log_level(self, audit_logger):
        """Test changing the log level."""
        audit_logger.set_log_level("DEBUG")
        assert audit_logger.logger.level == logging.DEBUG

        audit_logger.set_log_level("WARNING")
        assert audit_logger.logger.level == logging.WARNING

        audit_logger.set_log_level("ERROR")
        assert audit_logger.logger.level == logging.ERROR

    def test_add_file_handler(self, audit_logger, tmp_path):
        """Test adding a file handler for logging to a file."""
        log_file = tmp_path / "audit.log"

        audit_logger.add_file_handler(str(log_file), level="INFO")

        # Log a message
        audit_logger.log_request("user123", "Test request", datetime.now())

        # Verify file was created and contains JSON
        assert log_file.exists()
        log_content = log_file.read_text()
        log_data = json.loads(log_content.strip())

        assert log_data["event_type"] == "user_request"
        assert log_data["user_id"] == "user123"

    def test_logger_does_not_propagate(self, audit_logger):
        """Test that logger does not propagate to root logger."""
        assert audit_logger.logger.propagate is False

    def test_multiple_log_entries_are_valid_json(self, audit_logger, log_capture):
        """Test that multiple log entries are each valid JSON."""
        log_stream, handler = log_capture
        audit_logger.logger.addHandler(handler)

        # Log multiple entries
        audit_logger.log_request("user1", "Request 1", datetime.now())
        audit_logger.log_request("user2", "Request 2", datetime.now())
        audit_logger.log_model_usage("model1", 100, 0.001)

        log_output = log_stream.getvalue()
        log_lines = log_output.strip().split("\n")

        assert len(log_lines) == 3
        for line in log_lines:
            log_data = json.loads(line)
            assert "timestamp" in log_data
            assert "level" in log_data
            assert "message" in log_data
