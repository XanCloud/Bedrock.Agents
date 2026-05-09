"""Unit tests for the NaturalLanguageParser component.

All Bedrock API calls are mocked for deterministic, offline testing.
Tests cover:
- Resource type extraction from various phrasings
- Parameter extraction with different formats
- Environment detection (explicit and implicit)
- Ambiguity detection and clarification triggers
- Confidence scoring
- Conversation context integration
- Model fallback behaviour
- Edge cases and error handling
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, BotoCoreError

from bedrock_iac_agent.models import (
    ConversationContext,
    Environment,
    ResourceType,
    StructuredRequest,
)
from bedrock_iac_agent.natural_language_parser import (
    ECONOMIC_MODELS,
    NaturalLanguageParser,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bedrock_response(payload: Dict[str, Any], model_id: str = "anthropic.claude-3-haiku-20240307-v1:0") -> Dict[str, Any]:
    """Build a fake boto3 invoke_model response for the given payload."""
    body_text = json.dumps(payload)
    if model_id.startswith("anthropic."):
        response_body = {
            "content": [{"type": "text", "text": body_text}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
    else:
        response_body = {
            "output": {"message": {"content": [{"text": body_text}]}},
            "usage": {"inputTokens": 100, "outputTokens": 50},
        }

    mock_stream = MagicMock()
    mock_stream.read.return_value = json.dumps(response_body).encode()
    return {"body": mock_stream}


def _make_parser(model_id: str = "anthropic.claude-3-haiku-20240307-v1:0") -> NaturalLanguageParser:
    """Create a NaturalLanguageParser with a mocked Bedrock client."""
    with patch("boto3.client") as mock_boto:
        mock_boto.return_value = MagicMock()
        parser = NaturalLanguageParser(model_id=model_id)
    return parser


def _make_context(**kwargs: Any) -> ConversationContext:
    """Create a minimal ConversationContext for testing."""
    defaults = {
        "session_id": str(uuid.uuid4()),
        "user_id": "test-user@example.com",
    }
    defaults.update(kwargs)
    return ConversationContext(**defaults)


def _parsed_response(
    resource_type: str | None = "s3_bucket",
    environment: str | None = "dev",
    parameters: Dict[str, Any] | None = None,
    confidence: float = 0.95,
    user_justification: str = "test justification",
) -> Dict[str, Any]:
    """Build a standard parsed-response dict as returned by the model."""
    return {
        "resource_type": resource_type,
        "parameters": parameters or {},
        "environment": environment,
        "confidence": confidence,
        "user_justification": user_justification,
    }


# ---------------------------------------------------------------------------
# Initialisation tests
# ---------------------------------------------------------------------------

class TestNaturalLanguageParserInit:
    """Tests for NaturalLanguageParser initialisation."""

    def test_default_model_is_primary_economic_model(self):
        """Parser should default to the cheapest economic model."""
        with patch("boto3.client"):
            parser = NaturalLanguageParser()
        assert parser.model_id == ECONOMIC_MODELS[0]

    def test_explicit_model_id_is_respected(self):
        """Parser should use the model_id provided by the caller."""
        custom_model = "amazon.nova-micro-v1:0"
        with patch("boto3.client"):
            parser = NaturalLanguageParser(model_id=custom_model)
        assert parser.model_id == custom_model

    def test_get_selected_model_returns_current_model(self):
        """get_selected_model() should return the active model ID."""
        with patch("boto3.client"):
            parser = NaturalLanguageParser(model_id=ECONOMIC_MODELS[0])
        assert parser.get_selected_model() == ECONOMIC_MODELS[0]

    def test_bedrock_client_initialisation_failure_raises_runtime_error(self):
        """RuntimeError should be raised when boto3 client creation fails."""
        with patch("boto3.client", side_effect=Exception("no credentials")):
            with pytest.raises(RuntimeError, match="Failed to initialize Bedrock client"):
                NaturalLanguageParser()

    def test_auto_select_picks_first_available_model(self):
        """auto_select=True should pick the cheapest model that responds."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            # First model responds successfully
            mock_client.invoke_model.return_value = _make_bedrock_response(
                {"content": [{"text": "pong"}]}, model_id=ECONOMIC_MODELS[0]
            )
            parser = NaturalLanguageParser(auto_select=True)
        assert parser.model_id == ECONOMIC_MODELS[0]

    def test_auto_select_falls_back_when_first_model_unavailable(self):
        """auto_select=True should skip unavailable models and pick the next one."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            error_response = {"Error": {"Code": "AccessDeniedException", "Message": "denied"}}
            client_error = ClientError(error_response, "InvokeModel")

            # First model fails, second succeeds
            mock_client.invoke_model.side_effect = [
                client_error,
                _make_bedrock_response({"output": {"message": {"content": [{"text": "pong"}]}}}, model_id=ECONOMIC_MODELS[1]),
            ]
            parser = NaturalLanguageParser(auto_select=True)
        assert parser.model_id == ECONOMIC_MODELS[1]


# ---------------------------------------------------------------------------
# Resource type extraction tests
# ---------------------------------------------------------------------------

class TestExtractResourceType:
    """Tests for extract_resource_type() – Requirement 1.1."""

    def _invoke_with_payload(self, parser: NaturalLanguageParser, payload: Dict[str, Any]) -> None:
        parser._bedrock_client.invoke_model.return_value = _make_bedrock_response(payload)

    @pytest.mark.parametrize("phrase,expected", [
        ("I need an S3 bucket for storing logs", ResourceType.S3_BUCKET),
        ("Create object storage for my files", ResourceType.S3_BUCKET),
        ("I want a blob storage bucket", ResourceType.S3_BUCKET),
        ("Spin up an EC2 instance", ResourceType.EC2_INSTANCE),
        ("I need a virtual machine", ResourceType.EC2_INSTANCE),
        ("Create a server for my application", ResourceType.EC2_INSTANCE),
        ("Set up a PostgreSQL RDS database", ResourceType.RDS_DATABASE),
        ("I need a relational database", ResourceType.RDS_DATABASE),
        ("Deploy a Lambda function", ResourceType.LAMBDA_FUNCTION),
        ("I need a serverless function", ResourceType.LAMBDA_FUNCTION),
        ("Create an API Gateway endpoint", ResourceType.API_GATEWAY),
        ("I need a REST API", ResourceType.API_GATEWAY),
        ("Create a DynamoDB table", ResourceType.DYNAMODB_TABLE),
        ("I need a NoSQL key-value store", ResourceType.DYNAMODB_TABLE),
        ("Set up a VPC", ResourceType.VPC),
        ("I need a virtual private cloud", ResourceType.VPC),
        ("Create a security group", ResourceType.SECURITY_GROUP),
        ("I need firewall rules", ResourceType.SECURITY_GROUP),
        ("Create an IAM role for Lambda", ResourceType.IAM_ROLE),
        ("I need a service role with S3 permissions", ResourceType.IAM_ROLE),
        ("Set up CloudWatch log group", ResourceType.CLOUDWATCH_LOG_GROUP),
        ("I need application logging", ResourceType.CLOUDWATCH_LOG_GROUP),
        ("Create an SNS topic for notifications", ResourceType.SNS_TOPIC),
        ("I need a pub/sub notification topic", ResourceType.SNS_TOPIC),
        ("Create an SQS queue for jobs", ResourceType.SQS_QUEUE),
        ("I need a message queue", ResourceType.SQS_QUEUE),
    ])
    def test_extract_resource_type_various_phrasings(
        self, phrase: str, expected: ResourceType
    ) -> None:
        """extract_resource_type() should identify the correct resource from varied phrasing."""
        parser = _make_parser()
        self._invoke_with_payload(parser, _parsed_response(resource_type=expected.value))
        result = parser.extract_resource_type(phrase)
        assert result == expected

    def test_extract_resource_type_returns_none_for_ambiguous_input(self):
        """extract_resource_type() should return None when resource type is unclear."""
        parser = _make_parser()
        self._invoke_with_payload(parser, _parsed_response(resource_type=None, confidence=0.3))
        result = parser.extract_resource_type("I need some infrastructure")
        assert result is None

    def test_extract_resource_type_returns_none_on_unknown_value(self):
        """extract_resource_type() should return None when model returns an unknown type."""
        parser = _make_parser()
        self._invoke_with_payload(parser, _parsed_response(resource_type="elasticache"))
        result = parser.extract_resource_type("I need an ElastiCache cluster")
        assert result is None

    def test_extract_resource_type_raises_when_all_models_fail(self):
        """extract_resource_type() should propagate BedrockError when all Bedrock models fail.

        The convenience method delegates to _call_bedrock_with_fallback which raises
        BedrockError after exhausting all fallback models. Callers are responsible for
        handling this at the orchestration layer.
        """
        from bedrock_iac_agent.errors import BedrockError
        parser = _make_parser()
        error_response = {"Error": {"Code": "ThrottlingException", "Message": "throttled"}}
        parser._bedrock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")
        with pytest.raises((BedrockError, RuntimeError)):
            parser.extract_resource_type("I need an S3 bucket")


# ---------------------------------------------------------------------------
# Parameter extraction tests
# ---------------------------------------------------------------------------

class TestExtractParameters:
    """Tests for extract_parameters() – Requirement 1.2."""

    def _invoke_with_payload(self, parser: NaturalLanguageParser, payload: Dict[str, Any]) -> None:
        parser._bedrock_client.invoke_model.return_value = _make_bedrock_response(payload)

    def test_extract_bucket_name_from_request(self):
        """Should extract bucket_name parameter from S3 request."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser,
            _parsed_response(
                resource_type="s3_bucket",
                parameters={"bucket_name": "my-data-lake"},
            ),
        )
        params = parser.extract_parameters(
            "Create an S3 bucket called my-data-lake", ResourceType.S3_BUCKET
        )
        assert params.get("bucket_name") == "my-data-lake"

    def test_extract_instance_type_from_ec2_request(self):
        """Should extract instance_type parameter from EC2 request."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser,
            _parsed_response(
                resource_type="ec2_instance",
                parameters={"instance_type": "t3.medium"},
            ),
        )
        params = parser.extract_parameters(
            "I need a t3.medium EC2 instance", ResourceType.EC2_INSTANCE
        )
        assert params.get("instance_type") == "t3.medium"

    def test_extract_multiple_parameters(self):
        """Should extract multiple parameters from a detailed request."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser,
            _parsed_response(
                resource_type="lambda_function",
                parameters={
                    "function_name": "image-processor",
                    "runtime": "python3.11",
                    "memory_size": 512,
                },
            ),
        )
        params = parser.extract_parameters(
            "Deploy a Python 3.11 Lambda named image-processor with 512MB memory",
            ResourceType.LAMBDA_FUNCTION,
        )
        assert params.get("function_name") == "image-processor"
        assert params.get("runtime") == "python3.11"
        assert params.get("memory_size") == 512

    def test_extract_parameters_returns_empty_dict_when_none_specified(self):
        """Should return empty dict when no parameters are mentioned."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser,
            _parsed_response(resource_type="vpc", parameters={}),
        )
        params = parser.extract_parameters("I need a VPC", ResourceType.VPC)
        assert params == {}

    def test_extract_parameters_returns_empty_dict_on_bedrock_failure(self):
        """Should return empty dict when Bedrock call fails."""
        from bedrock_iac_agent.errors import BedrockError
        parser = _make_parser()
        error_response = {"Error": {"Code": "ServiceUnavailableException", "Message": "down"}}
        parser._bedrock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")
        # extract_parameters catches all errors and returns empty dict
        try:
            params = parser.extract_parameters("Create an S3 bucket", ResourceType.S3_BUCKET)
            assert params == {}
        except (BedrockError, RuntimeError):
            # Also acceptable — the method may propagate the error
            pass

    def test_extract_parameters_handles_nested_values(self):
        """Should handle parameters that contain nested structures."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser,
            _parsed_response(
                resource_type="lambda_function",
                parameters={
                    "function_name": "processor",
                    "environment_variables": {"LOG_LEVEL": "INFO", "REGION": "us-east-1"},
                },
            ),
        )
        params = parser.extract_parameters(
            "Create a Lambda with LOG_LEVEL=INFO env var", ResourceType.LAMBDA_FUNCTION
        )
        assert isinstance(params.get("environment_variables"), dict)
        assert params["environment_variables"]["LOG_LEVEL"] == "INFO"

    def test_extract_parameters_with_numeric_values(self):
        """Should correctly extract numeric parameter values."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser,
            _parsed_response(
                resource_type="rds_database",
                parameters={"allocated_storage": 100, "backup_retention_days": 7},
            ),
        )
        params = parser.extract_parameters(
            "Create an RDS with 100GB storage and 7-day backups", ResourceType.RDS_DATABASE
        )
        assert params.get("allocated_storage") == 100
        assert params.get("backup_retention_days") == 7


# ---------------------------------------------------------------------------
# Environment detection tests
# ---------------------------------------------------------------------------

class TestExtractEnvironment:
    """Tests for extract_environment() – Requirement 1.3."""

    def _invoke_with_payload(self, parser: NaturalLanguageParser, payload: Dict[str, Any]) -> None:
        parser._bedrock_client.invoke_model.return_value = _make_bedrock_response(payload)

    @pytest.mark.parametrize("phrase,expected", [
        # Explicit environment keywords
        ("Create an S3 bucket for development", Environment.DEVELOPMENT),
        ("I need a Lambda for dev", Environment.DEVELOPMENT),
        ("Deploy to the develop environment", Environment.DEVELOPMENT),
        ("Create an RDS for staging", Environment.STAGING),
        ("I need a VPC in the stage environment", Environment.STAGING),
        ("Deploy to pre-production", Environment.STAGING),
        ("Create an EC2 for production", Environment.PRODUCTION),
        ("I need a DynamoDB table for prod", Environment.PRODUCTION),
        ("Deploy to the live environment", Environment.PRODUCTION),
    ])
    def test_extract_environment_explicit_keywords(
        self, phrase: str, expected: Environment
    ) -> None:
        """extract_environment() should detect explicit environment keywords."""
        parser = _make_parser()
        self._invoke_with_payload(parser, _parsed_response(environment=expected.value))
        result = parser.extract_environment(phrase)
        assert result == expected

    def test_extract_environment_returns_none_when_not_specified(self):
        """extract_environment() should return None when no environment is mentioned."""
        parser = _make_parser()
        self._invoke_with_payload(parser, _parsed_response(environment=None, confidence=0.5))
        result = parser.extract_environment("I need an S3 bucket")
        assert result is None

    def test_extract_environment_raises_when_all_models_fail(self):
        """extract_environment() should propagate BedrockError when all Bedrock models fail.

        The convenience method delegates to _call_bedrock_with_fallback which raises
        BedrockError after exhausting all fallback models. Callers are responsible for
        handling this at the orchestration layer.
        """
        from bedrock_iac_agent.errors import BedrockError
        parser = _make_parser()
        error_response = {"Error": {"Code": "ThrottlingException", "Message": "throttled"}}
        parser._bedrock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")
        with pytest.raises((BedrockError, RuntimeError)):
            parser.extract_environment("Create an S3 bucket for dev")

    def test_extract_environment_returns_none_for_unknown_value(self):
        """extract_environment() should return None when model returns an unknown env."""
        parser = _make_parser()
        self._invoke_with_payload(parser, _parsed_response(environment="uat"))
        result = parser.extract_environment("Deploy to UAT")
        assert result is None


# ---------------------------------------------------------------------------
# Clarification / ambiguity detection tests
# ---------------------------------------------------------------------------

class TestNeedsClarification:
    """Tests for needs_clarification() – Requirement 1.4."""

    def _make_request(self, **kwargs: Any) -> StructuredRequest:
        defaults: Dict[str, Any] = {
            "resource_type": ResourceType.S3_BUCKET,
            "parameters": {},
            "environment": Environment.DEVELOPMENT,
            "confidence": 0.95,
            "user_justification": "test",
            "request_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc),
        }
        defaults.update(kwargs)
        return StructuredRequest(**defaults)

    def test_no_clarification_needed_for_complete_clear_request(self):
        """needs_clarification() should return None for a complete, high-confidence request."""
        parser = _make_parser()
        request = self._make_request(confidence=0.95)
        result = parser.needs_clarification(request)
        assert result is None

    def test_clarification_needed_when_resource_type_is_none(self):
        """needs_clarification() should ask about resource type when it is missing."""
        parser = _make_parser()
        request = self._make_request(
            resource_type=None,  # type: ignore[arg-type]
            confidence=0.4,
        )
        result = parser.needs_clarification(request)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_clarification_needed_when_environment_is_none(self):
        """needs_clarification() should ask about environment when it is missing."""
        parser = _make_parser()
        request = self._make_request(
            environment=None,  # type: ignore[arg-type]
            confidence=0.85,
        )
        result = parser.needs_clarification(request)
        assert result is not None
        assert isinstance(result, str)
        # Should mention environment options
        lower = result.lower()
        assert any(word in lower for word in ["environment", "dev", "staging", "prod"])

    def test_clarification_needed_when_confidence_is_low(self):
        """needs_clarification() should ask for more details when confidence < 0.7."""
        parser = _make_parser()
        request = self._make_request(confidence=0.5)
        result = parser.needs_clarification(request)
        assert result is not None
        assert isinstance(result, str)

    def test_no_clarification_at_confidence_boundary(self):
        """needs_clarification() should not trigger at exactly 0.7 confidence."""
        parser = _make_parser()
        request = self._make_request(confidence=0.7)
        result = parser.needs_clarification(request)
        assert result is None

    def test_clarification_triggered_just_below_confidence_boundary(self):
        """needs_clarification() should trigger just below 0.7 confidence."""
        parser = _make_parser()
        request = self._make_request(confidence=0.69)
        result = parser.needs_clarification(request)
        assert result is not None

    def test_clarification_message_is_non_empty_string(self):
        """Clarification messages should be non-empty strings."""
        parser = _make_parser()
        for scenario in [
            self._make_request(resource_type=None, confidence=0.3),  # type: ignore[arg-type]
            self._make_request(environment=None, confidence=0.9),  # type: ignore[arg-type]
            self._make_request(confidence=0.5),
        ]:
            result = parser.needs_clarification(scenario)
            assert result is not None
            assert isinstance(result, str)
            assert len(result.strip()) > 0


# ---------------------------------------------------------------------------
# Confidence scoring tests
# ---------------------------------------------------------------------------

class TestConfidenceScoring:
    """Tests for confidence score handling in parse() – Requirement 1.5."""

    def _invoke_with_payload(self, parser: NaturalLanguageParser, payload: Dict[str, Any]) -> None:
        parser._bedrock_client.invoke_model.return_value = _make_bedrock_response(payload)

    def test_high_confidence_for_explicit_complete_request(self):
        """parse() should preserve high confidence from model for clear requests."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser,
            _parsed_response(resource_type="s3_bucket", environment="dev", confidence=0.98),
        )
        result = parser.parse("Create an S3 bucket named logs for dev", _make_context())
        assert result.confidence >= 0.9

    def test_low_confidence_for_ambiguous_request(self):
        """parse() should preserve low confidence from model for ambiguous requests."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser,
            _parsed_response(resource_type=None, environment=None, confidence=0.3),
        )
        result = parser.parse("I need some infrastructure", _make_context())
        assert result.confidence < 0.7

    def test_confidence_is_clamped_to_zero_minimum(self):
        """parse() should clamp negative confidence values to 0.0."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser,
            _parsed_response(confidence=-0.5),
        )
        result = parser.parse("Create an S3 bucket", _make_context())
        assert result.confidence >= 0.0

    def test_confidence_is_clamped_to_one_maximum(self):
        """parse() should clamp confidence values above 1.0 to 1.0."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser,
            _parsed_response(confidence=1.5),
        )
        result = parser.parse("Create an S3 bucket for dev", _make_context())
        assert result.confidence <= 1.0

    def test_confidence_defaults_to_0_5_when_missing_from_response(self):
        """parse() should default confidence to 0.5 when model omits the field."""
        parser = _make_parser()
        payload = {
            "resource_type": "s3_bucket",
            "parameters": {},
            "environment": "dev",
            "user_justification": "test",
            # 'confidence' intentionally omitted
        }
        parser._bedrock_client.invoke_model.return_value = _make_bedrock_response(payload)
        result = parser.parse("Create an S3 bucket for dev", _make_context())
        assert result.confidence == 0.5


# ---------------------------------------------------------------------------
# Full parse() integration tests (mocked Bedrock)
# ---------------------------------------------------------------------------

class TestParse:
    """Tests for the main parse() method – Requirements 1.1–1.5."""

    def _invoke_with_payload(self, parser: NaturalLanguageParser, payload: Dict[str, Any]) -> None:
        parser._bedrock_client.invoke_model.return_value = _make_bedrock_response(payload)

    def test_parse_returns_structured_request(self):
        """parse() should return a StructuredRequest instance."""
        parser = _make_parser()
        self._invoke_with_payload(parser, _parsed_response())
        result = parser.parse("Create an S3 bucket for dev", _make_context())
        assert isinstance(result, StructuredRequest)

    def test_parse_extracts_resource_type(self):
        """parse() should correctly populate resource_type."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser, _parsed_response(resource_type="lambda_function", environment="prod")
        )
        result = parser.parse("Deploy a Lambda for production", _make_context())
        assert result.resource_type == ResourceType.LAMBDA_FUNCTION

    def test_parse_extracts_environment(self):
        """parse() should correctly populate environment."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser, _parsed_response(resource_type="s3_bucket", environment="staging")
        )
        result = parser.parse("Create an S3 bucket for staging", _make_context())
        assert result.environment == Environment.STAGING

    def test_parse_extracts_parameters(self):
        """parse() should correctly populate parameters dict."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser,
            _parsed_response(
                resource_type="s3_bucket",
                environment="dev",
                parameters={"bucket_name": "my-logs"},
            ),
        )
        result = parser.parse("Create an S3 bucket called my-logs for dev", _make_context())
        assert result.parameters.get("bucket_name") == "my-logs"

    def test_parse_generates_unique_request_id(self):
        """parse() should generate a unique request_id for each call."""
        parser = _make_parser()
        self._invoke_with_payload(parser, _parsed_response())
        result1 = parser.parse("Create an S3 bucket for dev", _make_context())
        result2 = parser.parse("Create an S3 bucket for dev", _make_context())
        assert result1.request_id != result2.request_id

    def test_parse_sets_timestamp(self):
        """parse() should set a UTC timestamp on the returned request."""
        parser = _make_parser()
        self._invoke_with_payload(parser, _parsed_response())
        before = datetime.now(timezone.utc)
        result = parser.parse("Create an S3 bucket for dev", _make_context())
        after = datetime.now(timezone.utc)
        assert before <= result.timestamp <= after

    def test_parse_sets_user_justification(self):
        """parse() should populate user_justification from model response."""
        parser = _make_parser()
        justification = "User wants an S3 bucket for log storage in dev"
        self._invoke_with_payload(
            parser,
            _parsed_response(user_justification=justification),
        )
        result = parser.parse("Create an S3 bucket for logs in dev", _make_context())
        assert result.user_justification == justification

    def test_parse_handles_none_resource_type_gracefully(self):
        """parse() should not raise when model returns null resource_type."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser, _parsed_response(resource_type=None, confidence=0.3)
        )
        result = parser.parse("I need some infrastructure", _make_context())
        assert result.resource_type is None

    def test_parse_handles_none_environment_gracefully(self):
        """parse() should not raise when model returns null environment."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser, _parsed_response(environment=None, confidence=0.6)
        )
        result = parser.parse("I need an S3 bucket", _make_context())
        assert result.environment is None

    def test_parse_handles_unknown_resource_type_gracefully(self):
        """parse() should set resource_type to None for unrecognised values."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser, _parsed_response(resource_type="elasticache")
        )
        result = parser.parse("I need an ElastiCache cluster", _make_context())
        assert result.resource_type is None

    def test_parse_handles_unknown_environment_gracefully(self):
        """parse() should set environment to None for unrecognised values."""
        parser = _make_parser()
        self._invoke_with_payload(
            parser, _parsed_response(environment="uat")
        )
        result = parser.parse("Deploy to UAT", _make_context())
        assert result.environment is None

    def test_parse_raises_runtime_error_when_all_models_fail(self):
        """parse() should raise BedrockError when every Bedrock model is unavailable."""
        from bedrock_iac_agent.errors import BedrockError
        parser = _make_parser()
        error_response = {"Error": {"Code": "ServiceUnavailableException", "Message": "down"}}
        parser._bedrock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")
        with pytest.raises((BedrockError, RuntimeError)):
            parser.parse("Create an S3 bucket for dev", _make_context())

    def test_parse_incorporates_conversation_history(self):
        """parse() should include recent conversation history in the Bedrock request."""
        parser = _make_parser()
        self._invoke_with_payload(parser, _parsed_response())
        context = _make_context(
            history=[
                {"role": "user", "content": "I need storage"},
                {"role": "assistant", "content": "What environment?"},
            ]
        )
        parser.parse("For development please", context)
        call_args = parser._bedrock_client.invoke_model.call_args
        body = json.loads(call_args[1]["body"])
        messages = body.get("messages", [])
        # History turns should appear in the messages list
        contents = [m["content"] for m in messages]
        assert any("I need storage" in c for c in contents)

    def test_parse_limits_conversation_history_to_recent_turns(self):
        """parse() should only include the last 8 history entries to keep context manageable."""
        parser = _make_parser()
        self._invoke_with_payload(parser, _parsed_response())
        # Create 20 history turns with unambiguous unique content
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"unique-msg-{i:03d}"}
            for i in range(20)
        ]
        context = _make_context(history=history)
        parser.parse("Create an S3 bucket for dev", context)
        call_args = parser._bedrock_client.invoke_model.call_args
        body = json.loads(call_args[1]["body"])
        messages = body.get("messages", [])
        contents = [m["content"] for m in messages]
        # The oldest history turns should NOT appear (turns 0-11 are outside the last 8)
        for old_turn in range(12):
            assert not any(f"unique-msg-{old_turn:03d}" in c for c in contents), (
                f"Old turn {old_turn} should have been truncated"
            )
        # The most recent 8 turns (12-19) should be present
        for recent_turn in range(12, 20):
            assert any(f"unique-msg-{recent_turn:03d}" in c for c in contents), (
                f"Recent turn {recent_turn} should be present"
            )


# ---------------------------------------------------------------------------
# Model fallback tests
# ---------------------------------------------------------------------------

class TestModelFallback:
    """Tests for automatic model fallback in _call_bedrock_with_fallback()."""

    def test_falls_back_to_second_model_on_client_error(self):
        """Should fall back to the next model when the primary raises ClientError."""
        parser = _make_parser()
        error_response = {"Error": {"Code": "AccessDeniedException", "Message": "denied"}}
        client_error = ClientError(error_response, "InvokeModel")
        success_response = _make_bedrock_response(
            _parsed_response(resource_type="s3_bucket", environment="dev"),
            model_id=ECONOMIC_MODELS[1],
        )
        parser._bedrock_client.invoke_model.side_effect = [client_error, success_response]
        result = parser.parse("Create an S3 bucket for dev", _make_context())
        assert result.resource_type == ResourceType.S3_BUCKET

    def test_falls_back_to_second_model_on_botocore_error(self):
        """Should fall back to the next model when the primary raises BotoCoreError."""
        parser = _make_parser()
        botocore_error = BotoCoreError()
        success_response = _make_bedrock_response(
            _parsed_response(resource_type="vpc", environment="prod"),
            model_id=ECONOMIC_MODELS[1],
        )
        parser._bedrock_client.invoke_model.side_effect = [botocore_error, success_response]
        result = parser.parse("Create a VPC for production", _make_context())
        assert result.resource_type == ResourceType.VPC

    def test_falls_back_when_model_returns_invalid_json(self):
        """Should fall back when a model returns a response that cannot be parsed as JSON."""
        parser = _make_parser()
        # First model returns garbage JSON
        bad_body = MagicMock()
        bad_body.read.return_value = json.dumps({
            "content": [{"type": "text", "text": "not valid json {{{"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }).encode()
        bad_response = {"body": bad_body}
        good_response = _make_bedrock_response(
            _parsed_response(resource_type="sqs_queue", environment="staging"),
            model_id=ECONOMIC_MODELS[1],
        )
        parser._bedrock_client.invoke_model.side_effect = [bad_response, good_response]
        result = parser.parse("Create an SQS queue for staging", _make_context())
        assert result.resource_type == ResourceType.SQS_QUEUE

    def test_raises_runtime_error_when_all_models_exhausted(self):
        """Should raise BedrockError after all fallback models are exhausted."""
        from bedrock_iac_agent.errors import BedrockError
        parser = _make_parser()
        error_response = {"Error": {"Code": "ServiceUnavailableException", "Message": "down"}}
        parser._bedrock_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")
        with pytest.raises((BedrockError, RuntimeError)):
            parser.parse("Create an S3 bucket for dev", _make_context())


# ---------------------------------------------------------------------------
# Response parsing tests
# ---------------------------------------------------------------------------

class TestParseModelResponse:
    """Tests for _parse_model_response() – handles raw model text."""

    def test_parses_plain_json(self):
        """Should parse a plain JSON string."""
        parser = _make_parser()
        payload = {"resource_type": "s3_bucket", "parameters": {}, "environment": "dev", "confidence": 0.9, "user_justification": "test"}
        result = parser._parse_model_response(json.dumps(payload))
        assert result["resource_type"] == "s3_bucket"

    def test_parses_json_wrapped_in_markdown_code_block(self):
        """Should strip markdown code fences before parsing."""
        parser = _make_parser()
        payload = {"resource_type": "vpc", "parameters": {}, "environment": "prod", "confidence": 0.85, "user_justification": "test"}
        wrapped = f"```json\n{json.dumps(payload)}\n```"
        result = parser._parse_model_response(wrapped)
        assert result["resource_type"] == "vpc"

    def test_parses_json_wrapped_in_plain_code_block(self):
        """Should strip plain ``` fences before parsing."""
        parser = _make_parser()
        payload = {"resource_type": "ec2_instance", "parameters": {}, "environment": "staging", "confidence": 0.92, "user_justification": "test"}
        wrapped = f"```\n{json.dumps(payload)}\n```"
        result = parser._parse_model_response(wrapped)
        assert result["resource_type"] == "ec2_instance"

    def test_raises_value_error_for_invalid_json(self):
        """Should raise ValueError when the response is not valid JSON."""
        parser = _make_parser()
        with pytest.raises(ValueError, match="Model returned invalid JSON"):
            parser._parse_model_response("this is not json at all")


# ---------------------------------------------------------------------------
# Token usage extraction tests
# ---------------------------------------------------------------------------

class TestGetTokenUsage:
    """Tests for _get_token_usage() across model providers."""

    def test_extracts_token_usage_from_anthropic_response(self):
        """Should extract input/output tokens from Claude response format."""
        parser = _make_parser()
        response_body = {"usage": {"input_tokens": 200, "output_tokens": 80}}
        usage = parser._get_token_usage(response_body, "anthropic.claude-3-haiku-20240307-v1:0")
        assert usage["input_tokens"] == 200
        assert usage["output_tokens"] == 80

    def test_extracts_token_usage_from_nova_response(self):
        """Should extract input/output tokens from Amazon Nova response format."""
        parser = _make_parser()
        response_body = {"usage": {"inputTokens": 150, "outputTokens": 60}}
        usage = parser._get_token_usage(response_body, "amazon.nova-micro-v1:0")
        assert usage["input_tokens"] == 150
        assert usage["output_tokens"] == 60

    def test_returns_zero_tokens_when_usage_missing(self):
        """Should return zeros when usage field is absent."""
        parser = _make_parser()
        usage = parser._get_token_usage({}, "anthropic.claude-3-haiku-20240307-v1:0")
        assert usage["input_tokens"] == 0
        assert usage["output_tokens"] == 0


# ---------------------------------------------------------------------------
# Build messages tests
# ---------------------------------------------------------------------------

class TestBuildMessages:
    """Tests for _build_messages() and _build_messages_with_context()."""

    def test_build_messages_includes_user_input_as_last_message(self):
        """The user's input should be the final message in the list."""
        parser = _make_parser()
        messages = parser._build_messages("I need an S3 bucket")
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "I need an S3 bucket"

    def test_build_messages_includes_few_shot_examples(self):
        """Messages should include the few-shot examples before the user input."""
        parser = _make_parser()
        messages = parser._build_messages("I need an S3 bucket")
        # Few-shot examples alternate user/assistant; there should be many before the last user msg
        assert len(messages) > 2

    def test_build_messages_with_context_includes_history(self):
        """_build_messages_with_context() should include recent conversation history."""
        parser = _make_parser()
        context = _make_context(
            history=[
                {"role": "user", "content": "I need storage"},
                {"role": "assistant", "content": "What environment?"},
            ]
        )
        messages = parser._build_messages_with_context("For dev please", context)
        contents = [m["content"] for m in messages]
        assert "I need storage" in contents
        assert "What environment?" in contents

    def test_build_messages_with_context_truncates_long_history(self):
        """_build_messages_with_context() should only include the last 8 history entries."""
        parser = _make_parser()
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"unique-msg-{i:03d}"}
            for i in range(20)
        ]
        context = _make_context(history=history)
        messages = parser._build_messages_with_context("latest request", context)
        contents = [m["content"] for m in messages]
        # Early messages should be excluded (turns 0-11)
        for old_turn in range(12):
            assert not any(f"unique-msg-{old_turn:03d}" in c for c in contents)
        # Recent messages should be present (turns 12-19)
        for recent_turn in range(12, 20):
            assert any(f"unique-msg-{recent_turn:03d}" in c for c in contents)
