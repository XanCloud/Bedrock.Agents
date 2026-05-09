"""Audit logging component for the Bedrock IaC Agent."""

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from bedrock_iac_agent.models import StructuredRequest, ResourceType, Environment


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "event_type"):
            log_data["event_type"] = record.event_type
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "resource_type"):
            log_data["resource_type"] = record.resource_type
        if hasattr(record, "environment"):
            log_data["environment"] = record.environment
        if hasattr(record, "model_used"):
            log_data["model_used"] = record.model_used
        if hasattr(record, "tokens_consumed"):
            log_data["tokens_consumed"] = record.tokens_consumed
        if hasattr(record, "cost"):
            log_data["cost"] = record.cost
        if hasattr(record, "pr_url"):
            log_data["pr_url"] = record.pr_url
        if hasattr(record, "status"):
            log_data["status"] = record.status
        if hasattr(record, "error_code"):
            log_data["error_code"] = record.error_code
        if hasattr(record, "stack_trace"):
            log_data["stack_trace"] = record.stack_trace

        # Add any additional context
        if hasattr(record, "context"):
            log_data["context"] = record.context

        return json.dumps(log_data)


class AuditLogger:
    """Audit logger for tracking all agent actions with structured JSON logging."""

    def __init__(self, logger_name: str = "bedrock_iac_agent.audit") -> None:
        """
        Initialize the audit logger.

        Args:
            logger_name: Name for the logger instance
        """
        self.logger = logging.getLogger(logger_name)
        self._configure_logger()

    def _configure_logger(self) -> None:
        """Configure the logger with JSON formatter and handlers."""
        # Set default level to INFO
        self.logger.setLevel(logging.INFO)

        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()

        # Console handler with JSON formatter
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(JSONFormatter())
        self.logger.addHandler(console_handler)

        # Prevent propagation to root logger
        self.logger.propagate = False

    def log_request(
        self,
        user_id: str,
        request: str,
        timestamp: datetime,
        request_id: Optional[str] = None,
    ) -> None:
        """
        Log a user request.

        Args:
            user_id: Identifier for the user making the request
            request: The natural language request text
            timestamp: When the request was made
            request_id: Optional unique identifier for the request
        """
        extra = {
            "event_type": "user_request",
            "user_id": user_id,
            "request_id": request_id or f"req-{timestamp.timestamp()}",
            "status": "received",
        }
        self.logger.info(f"User request received: {request[:100]}...", extra=extra)

    def log_configuration(
        self,
        config: StructuredRequest,
        tfvars_content: str,
    ) -> None:
        """
        Log a generated configuration.

        Args:
            config: The structured request containing configuration details
            tfvars_content: The generated tfvars file content
        """
        extra = {
            "event_type": "configuration_generated",
            "request_id": config.request_id,
            "resource_type": config.resource_type.value,
            "environment": config.environment.value,
            "status": "generated",
            "context": {
                "confidence": config.confidence,
                "parameters": list(config.parameters.keys()),
                "tfvars_size": len(tfvars_content),
            },
        }
        self.logger.info(
            f"Configuration generated for {config.resource_type.value} in {config.environment.value}",
            extra=extra,
        )

    def log_pull_request(
        self,
        pr_url: str,
        request_id: str,
        resource_type: Optional[ResourceType] = None,
        environment: Optional[Environment] = None,
    ) -> None:
        """
        Log Pull Request creation.

        Args:
            pr_url: URL of the created Pull Request
            request_id: Identifier linking to the original request
            resource_type: Type of resource being deployed
            environment: Target deployment environment
        """
        extra = {
            "event_type": "pull_request_created",
            "request_id": request_id,
            "pr_url": pr_url,
            "status": "success",
        }
        if resource_type:
            extra["resource_type"] = resource_type.value
        if environment:
            extra["environment"] = environment.value

        self.logger.info(f"Pull Request created: {pr_url}", extra=extra)

    def log_model_usage(
        self,
        model_name: str,
        tokens_consumed: int,
        cost: float,
        request_id: Optional[str] = None,
    ) -> None:
        """
        Log Bedrock model usage for cost tracking.

        Args:
            model_name: Name of the Bedrock model used
            tokens_consumed: Number of tokens consumed
            cost: Estimated cost in USD
            request_id: Optional identifier linking to the request
        """
        extra = {
            "event_type": "model_usage",
            "model_used": model_name,
            "tokens_consumed": tokens_consumed,
            "cost": cost,
            "status": "completed",
        }
        if request_id:
            extra["request_id"] = request_id

        self.logger.info(
            f"Model usage: {model_name} - {tokens_consumed} tokens (${cost:.4f})",
            extra=extra,
        )

    def log_error(
        self,
        error: Exception,
        context: Dict[str, Any],
        error_code: Optional[str] = None,
    ) -> None:
        """
        Log errors with context and stack trace.

        Args:
            error: The exception that occurred
            context: Additional context about the error (user_id, request_id, etc.)
            error_code: Optional error code for categorization
        """
        stack_trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        extra = {
            "event_type": "error",
            "error_code": error_code or type(error).__name__,
            "status": "error",
            "stack_trace": stack_trace,
            "context": context,
        }

        # Add context fields to top level if present
        if "user_id" in context:
            extra["user_id"] = context["user_id"]
        if "request_id" in context:
            extra["request_id"] = context["request_id"]
        if "resource_type" in context:
            extra["resource_type"] = context["resource_type"]
        if "environment" in context:
            extra["environment"] = context["environment"]

        self.logger.error(f"Error occurred: {str(error)}", extra=extra)

    def set_log_level(self, level: str) -> None:
        """
        Set the logging level.

        Args:
            level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        numeric_level = getattr(logging, level.upper(), logging.INFO)
        self.logger.setLevel(numeric_level)
        for handler in self.logger.handlers:
            handler.setLevel(numeric_level)

    def add_file_handler(self, log_file_path: str, level: str = "INFO") -> None:
        """
        Add a file handler for logging to a file.

        Args:
            log_file_path: Path to the log file
            level: Logging level for the file handler
        """
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        file_handler.setFormatter(JSONFormatter())
        self.logger.addHandler(file_handler)

    def add_rotating_file_handler(
        self,
        log_file_path: str,
        level: str = "INFO",
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        """
        Add a rotating file handler for production log management.

        Uses :class:`~logging.handlers.RotatingFileHandler` to cap individual
        log files at *max_bytes* and keep *backup_count* rotated copies.

        Args:
            log_file_path: Path to the log file.  Parent directories are
                created automatically if they do not exist.
            level: Logging level for the file handler (DEBUG, INFO, etc.)
            max_bytes: Maximum size in bytes before the file is rotated.
                Defaults to 10 MB.
            backup_count: Number of rotated backup files to retain.
                Defaults to 5.
        """
        import logging.handlers  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)

        rotating_handler = logging.handlers.RotatingFileHandler(
            filename=log_file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        rotating_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        rotating_handler.setFormatter(JSONFormatter())
        self.logger.addHandler(rotating_handler)
