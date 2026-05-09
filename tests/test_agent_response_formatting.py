"""Unit tests for BedrockIaCAgent AgentResponse formatting methods.

Tests cover requirements 7.1–7.4:
  7.1 - Notify user with full PR URL when PR is created
  7.2 - Provide summary of changes made
  7.3 - Indicate next steps required (review, approval, merge)
  7.4 - On error, provide descriptive error message and corrective actions
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from bedrock_iac_agent.agent import BedrockIaCAgent
from bedrock_iac_agent.errors import (
    AgentError,
    AuthenticationError,
    GenerationError,
    NetworkError,
    ValidationError,
)
from bedrock_iac_agent.models import (
    AgentResponse,
    ConversationContext,
    Environment,
    ResourceType,
    StructuredRequest,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_SENTINEL = object()


def _make_request(
    resource_type: ResourceType = ResourceType.S3_BUCKET,
    environment: Environment = Environment.DEVELOPMENT,
    parameters: Any = _SENTINEL,
    justification: str = "Need storage for logs",
) -> StructuredRequest:
    if parameters is _SENTINEL:
        parameters = {"bucket_name": "my-logs"}
    return StructuredRequest(
        resource_type=resource_type,
        parameters=parameters,
        environment=environment,
        confidence=0.95,
        user_justification=justification,
        request_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
    )


def _make_context(session_id: str = "sess-001", user_id: str = "dev@example.com") -> ConversationContext:
    return ConversationContext(session_id=session_id, user_id=user_id)


def _make_agent() -> BedrockIaCAgent:
    """Create a BedrockIaCAgent with all dependencies mocked."""
    nlp_parser = MagicMock()
    config_generator = MagicMock()
    modules_inventory = MagicMock()
    audit_logger = MagicMock()

    agent = BedrockIaCAgent(
        nlp_parser=nlp_parser,
        config_generator=config_generator,
        modules_inventory=modules_inventory,
        audit_logger=audit_logger,
    )
    return agent


# ---------------------------------------------------------------------------
# Tests for _build_success_response (Requirements 7.1, 7.2, 7.3)
# ---------------------------------------------------------------------------


class TestBuildSuccessResponse:
    """Tests for _build_success_response."""

    def test_status_is_success(self):
        agent = _make_agent()
        request = _make_request()
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/42")
        assert response.status == "success"

    def test_pr_url_included_in_message(self):
        """Requirement 7.1: Notify user with the full PR URL."""
        agent = _make_agent()
        request = _make_request()
        pr_url = "https://github.com/org/repo/pull/42"
        response = agent._build_success_response(request, pr_url=pr_url)
        assert pr_url in response.message

    def test_pr_url_set_on_response(self):
        """Requirement 7.1: The pr_url field is populated."""
        agent = _make_agent()
        request = _make_request()
        pr_url = "https://github.com/org/repo/pull/99"
        response = agent._build_success_response(request, pr_url=pr_url)
        assert response.pr_url == pr_url

    def test_resource_type_in_message(self):
        """Requirement 7.2: Summary includes the resource type."""
        agent = _make_agent()
        request = _make_request(resource_type=ResourceType.LAMBDA_FUNCTION)
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        assert "lambda_function" in response.message

    def test_environment_in_message(self):
        """Requirement 7.2: Summary includes the environment."""
        agent = _make_agent()
        request = _make_request(environment=Environment.PRODUCTION)
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        assert "prod" in response.message

    def test_parameters_in_summary(self):
        """Requirement 7.2: Summary includes configured parameters."""
        agent = _make_agent()
        request = _make_request(parameters={"bucket_name": "my-logs", "region": "us-east-1"})
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        assert "bucket_name" in response.message
        assert "my-logs" in response.message
        assert "region" in response.message
        assert "us-east-1" in response.message

    def test_justification_in_summary(self):
        """Requirement 7.2: Summary includes the user justification."""
        agent = _make_agent()
        request = _make_request(justification="Storing application logs for 90 days")
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        assert "Storing application logs for 90 days" in response.message

    def test_next_steps_include_review_url(self):
        """Requirement 7.3: Next steps include a link to review the PR."""
        agent = _make_agent()
        request = _make_request()
        pr_url = "https://github.com/org/repo/pull/42"
        response = agent._build_success_response(request, pr_url=pr_url)
        assert any(pr_url in step for step in response.next_steps)

    def test_next_steps_include_approve_and_merge(self):
        """Requirement 7.3: Next steps mention approval and merge."""
        agent = _make_agent()
        request = _make_request()
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        steps_text = " ".join(response.next_steps).lower()
        # Accept both English and Spanish keywords
        assert ("approve" in steps_text or "aprueba" in steps_text or "aprobación" in steps_text)
        assert ("merge" in steps_text or "haz merge" in steps_text)

    def test_next_steps_not_empty(self):
        """Requirement 7.3: Next steps list is never empty."""
        agent = _make_agent()
        request = _make_request()
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        assert len(response.next_steps) > 0

    def test_metadata_contains_request_id(self):
        agent = _make_agent()
        request = _make_request()
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        assert response.metadata["request_id"] == request.request_id

    def test_metadata_contains_resource_type(self):
        agent = _make_agent()
        request = _make_request(resource_type=ResourceType.RDS_DATABASE)
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        assert response.metadata["resource_type"] == "rds_database"

    def test_metadata_contains_environment(self):
        agent = _make_agent()
        request = _make_request(environment=Environment.STAGING)
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        assert response.metadata["environment"] == "staging"

    def test_no_pr_url_when_github_not_configured(self):
        """When GitHub integration is not configured, pr_url is None."""
        agent = _make_agent()
        request = _make_request()
        response = agent._build_success_response(request, pr_url=None)
        assert response.pr_url is None
        assert response.status == "success"

    def test_no_pr_url_message_mentions_github_not_configured(self):
        agent = _make_agent()
        request = _make_request()
        response = agent._build_success_response(request, pr_url=None)
        # Accept both English and Spanish
        msg_lower = response.message.lower()
        assert "github integration not configured" in msg_lower or "integración con github no configurada" in msg_lower

    def test_no_pr_url_next_steps_guide_configuration(self):
        agent = _make_agent()
        request = _make_request()
        response = agent._build_success_response(request, pr_url=None)
        steps_text = " ".join(response.next_steps).lower()
        assert "github" in steps_text or "configure" in steps_text

    def test_empty_parameters_shows_defaults_message(self):
        """When no parameters are provided, summary mentions using defaults."""
        agent = _make_agent()
        request = _make_request(parameters={})
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        assert "default" in response.message.lower()


# ---------------------------------------------------------------------------
# Tests for _format_changes_summary (Requirement 7.2)
# ---------------------------------------------------------------------------


class TestFormatChangesSummary:
    """Tests for _format_changes_summary."""

    def test_returns_string(self):
        agent = _make_agent()
        request = _make_request()
        result = agent._format_changes_summary(request)
        assert isinstance(result, str)

    def test_includes_all_parameters(self):
        agent = _make_agent()
        request = _make_request(parameters={"key1": "val1", "key2": "val2"})
        result = agent._format_changes_summary(request)
        assert "key1" in result
        assert "val1" in result
        assert "key2" in result
        assert "val2" in result

    def test_includes_justification(self):
        agent = _make_agent()
        request = _make_request(justification="For compliance reasons")
        result = agent._format_changes_summary(request)
        assert "For compliance reasons" in result

    def test_empty_parameters_handled_gracefully(self):
        agent = _make_agent()
        request = _make_request(parameters={})
        result = agent._format_changes_summary(request)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_justification_handled_gracefully(self):
        agent = _make_agent()
        request = _make_request(justification="")
        result = agent._format_changes_summary(request)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Tests for _build_needs_clarification_response (Requirement 1.4)
# ---------------------------------------------------------------------------


class TestBuildNeedsClarificationResponse:
    """Tests for _build_needs_clarification_response."""

    def test_status_is_needs_clarification(self):
        agent = _make_agent()
        response = agent._build_needs_clarification_response(
            question="Which environment?", request_id="req-001"
        )
        assert response.status == "needs_clarification"

    def test_question_is_in_message(self):
        agent = _make_agent()
        question = "Which environment should this be deployed to?"
        response = agent._build_needs_clarification_response(question=question, request_id="req-001")
        assert question in response.message

    def test_request_id_in_metadata(self):
        agent = _make_agent()
        response = agent._build_needs_clarification_response(
            question="Which environment?", request_id="req-xyz"
        )
        assert response.metadata["request_id"] == "req-xyz"

    def test_next_steps_not_empty(self):
        agent = _make_agent()
        response = agent._build_needs_clarification_response(
            question="Which environment?", request_id="req-001"
        )
        assert len(response.next_steps) > 0

    def test_pr_url_is_none(self):
        agent = _make_agent()
        response = agent._build_needs_clarification_response(
            question="Which environment?", request_id="req-001"
        )
        assert response.pr_url is None


# ---------------------------------------------------------------------------
# Tests for _handle_error (Requirement 7.4)
# ---------------------------------------------------------------------------


class TestHandleError:
    """Tests for _handle_error."""

    def test_status_is_error(self):
        agent = _make_agent()
        context = _make_context()
        exc = AuthenticationError("Token expired")
        response = agent._handle_error(exc, context, "error")
        assert response.status == "error"

    def test_error_message_in_response(self):
        """Requirement 7.4: Descriptive error message is included."""
        agent = _make_agent()
        context = _make_context()
        exc = AuthenticationError("Your GitHub token has expired")
        response = agent._handle_error(exc, context, "error")
        assert "Your GitHub token has expired" in response.message

    def test_suggested_actions_from_exception(self):
        """Requirement 7.4: Corrective actions from the exception are included."""
        agent = _make_agent()
        context = _make_context()
        exc = AuthenticationError(
            "Token expired",
            suggested_actions=["Regenerate your GitHub token", "Update config.yaml"],
        )
        response = agent._handle_error(exc, context, "error")
        assert "Regenerate your GitHub token" in response.next_steps
        assert "Update config.yaml" in response.next_steps

    def test_fallback_next_steps_when_no_suggested_actions(self):
        """Requirement 7.4: Fallback corrective actions when none are provided."""
        agent = _make_agent()
        context = _make_context()
        exc = AgentError("Something went wrong", suggested_actions=[])
        response = agent._handle_error(exc, context, "error")
        assert len(response.next_steps) > 0

    def test_error_code_in_metadata(self):
        agent = _make_agent()
        context = _make_context()
        exc = ValidationError("Bad param", error_code="INVALID_PARAMS")
        response = agent._handle_error(exc, context, "error")
        assert response.metadata["error_code"] == "INVALID_PARAMS"

    def test_retry_possible_in_metadata(self):
        agent = _make_agent()
        context = _make_context()
        exc = NetworkError("Timeout", retry_possible=True)
        response = agent._handle_error(exc, context, "error")
        assert response.metadata["retry_possible"] is True

    def test_error_appended_to_history(self):
        agent = _make_agent()
        context = _make_context()
        exc = GenerationError("HCL syntax error")
        agent._handle_error(exc, context, "error")
        assert any(m["role"] == "assistant" for m in context.history)

    def test_audit_logger_called(self):
        agent = _make_agent()
        context = _make_context()
        exc = AuthenticationError("Token expired")
        agent._handle_error(exc, context, "error")
        agent.audit_logger.log_error.assert_called_once()

    def test_network_error_has_retry_true(self):
        agent = _make_agent()
        context = _make_context()
        exc = NetworkError()
        response = agent._handle_error(exc, context, "error")
        assert response.metadata["retry_possible"] is True

    def test_auth_error_has_retry_false(self):
        agent = _make_agent()
        context = _make_context()
        exc = AuthenticationError()
        response = agent._handle_error(exc, context, "error")
        assert response.metadata["retry_possible"] is False


# ---------------------------------------------------------------------------
# Tests for AgentResponse structure (all requirements)
# ---------------------------------------------------------------------------


class TestAgentResponseStructure:
    """Verify AgentResponse objects have the correct structure."""

    def test_success_response_is_agent_response_instance(self):
        agent = _make_agent()
        request = _make_request()
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        assert isinstance(response, AgentResponse)

    def test_error_response_is_agent_response_instance(self):
        agent = _make_agent()
        context = _make_context()
        exc = AgentError("Something failed")
        response = agent._handle_error(exc, context, "error")
        assert isinstance(response, AgentResponse)

    def test_clarification_response_is_agent_response_instance(self):
        agent = _make_agent()
        response = agent._build_needs_clarification_response("Which env?", "req-1")
        assert isinstance(response, AgentResponse)

    def test_valid_status_values(self):
        """Status must be one of the three defined values."""
        valid_statuses = {"success", "error", "needs_clarification"}
        agent = _make_agent()
        request = _make_request()
        context = _make_context()

        success_resp = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        error_resp = agent._handle_error(AgentError("err"), context, "error")
        clarif_resp = agent._build_needs_clarification_response("Q?", "req-1")

        assert success_resp.status in valid_statuses
        assert error_resp.status in valid_statuses
        assert clarif_resp.status in valid_statuses

    def test_next_steps_is_list(self):
        agent = _make_agent()
        request = _make_request()
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        assert isinstance(response.next_steps, list)

    def test_metadata_is_dict(self):
        agent = _make_agent()
        request = _make_request()
        response = agent._build_success_response(request, pr_url="https://github.com/org/repo/pull/1")
        assert isinstance(response.metadata, dict)
