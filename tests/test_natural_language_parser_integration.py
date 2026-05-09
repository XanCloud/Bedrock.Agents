"""Integration tests for the NaturalLanguageParser with actual Bedrock models.

These tests call real AWS Bedrock APIs and are skipped gracefully when
AWS credentials are not available or Bedrock is not accessible.

Run integration tests with:
    pytest tests/test_natural_language_parser_integration.py -m integration -v

Requirements validated:
    - 2.1: Agent SHALL use economic Bedrock models (Haiku, Minimax, Qwen or similar)
    - 2.2: Agent SHALL select the model with best cost-performance ratio
    - 2.3: Agent SHALL log the model used in each interaction for cost auditing
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import pytest

# ---------------------------------------------------------------------------
# Availability check – runs once at collection time
# ---------------------------------------------------------------------------

def _check_bedrock_available() -> Tuple[bool, str]:
    """
    Check whether AWS credentials and Bedrock access are available.

    Returns:
        (available: bool, reason: str)
    """
    try:
        import boto3
        from botocore.exceptions import ClientError, BotoCoreError, NoCredentialsError

        client = boto3.client("bedrock-runtime")
        # Minimal ping to the cheapest model
        import json

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "hi"}],
        })
        client.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


_BEDROCK_AVAILABLE, _BEDROCK_SKIP_REASON = _check_bedrock_available()

requires_bedrock = pytest.mark.skipif(
    not _BEDROCK_AVAILABLE,
    reason=f"AWS Bedrock not available: {_BEDROCK_SKIP_REASON}",
)

# ---------------------------------------------------------------------------
# Model definitions for parametrized tests
# ---------------------------------------------------------------------------

# The three economic model families mentioned in the requirements.
# Each entry is (label, model_id).  Haiku is the primary; the others are
# the Amazon Nova models that serve as the Minimax/Qwen equivalents in the
# current ECONOMIC_MODELS list.
INTEGRATION_MODELS: List[Tuple[str, str]] = [
    ("haiku", "anthropic.claude-3-haiku-20240307-v1:0"),
    ("nova-micro", "amazon.nova-micro-v1:0"),   # Minimax equivalent
    ("nova-lite", "amazon.nova-lite-v1:0"),      # Qwen equivalent
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(**kwargs: Any):  # type: ignore[return]
    """Create a minimal ConversationContext."""
    from bedrock_iac_agent.models import ConversationContext

    defaults = {
        "session_id": str(uuid.uuid4()),
        "user_id": "integration-test@example.com",
    }
    defaults.update(kwargs)
    return ConversationContext(**defaults)


def _make_parser(model_id: str):  # type: ignore[return]
    """Create a real NaturalLanguageParser (no mocks)."""
    from bedrock_iac_agent.natural_language_parser import NaturalLanguageParser

    return NaturalLanguageParser(model_id=model_id)


# ---------------------------------------------------------------------------
# Integration test suite
# ---------------------------------------------------------------------------

@requires_bedrock
@pytest.mark.integration
class TestNaturalLanguageParserIntegration:
    """
    Integration tests that call actual Bedrock APIs.

    **Validates: Requirements 2.1, 2.2, 2.3**
    """

    # ------------------------------------------------------------------
    # Per-model parsing tests (parametrized)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("model_label,model_id", INTEGRATION_MODELS)
    def test_parse_s3_request_with_model(self, model_label: str, model_id: str) -> None:
        """
        Each economic model should correctly parse an S3 bucket request.

        **Validates: Requirement 2.1** – agent uses economic Bedrock models.
        """
        from bedrock_iac_agent.models import Environment, ResourceType

        parser = _make_parser(model_id)
        context = _make_context()

        result = parser.parse(
            "I need an S3 bucket called integration-test-logs for development",
            context,
        )

        assert result.resource_type == ResourceType.S3_BUCKET, (
            f"[{model_label}] Expected S3_BUCKET, got {result.resource_type}"
        )
        assert result.environment == Environment.DEVELOPMENT, (
            f"[{model_label}] Expected DEVELOPMENT, got {result.environment}"
        )
        assert result.confidence >= 0.7, (
            f"[{model_label}] Expected confidence >= 0.7, got {result.confidence}"
        )

    @pytest.mark.parametrize("model_label,model_id", INTEGRATION_MODELS)
    def test_parse_ec2_request_with_model(self, model_label: str, model_id: str) -> None:
        """
        Each economic model should correctly parse an EC2 instance request.

        **Validates: Requirement 2.1** – agent uses economic Bedrock models.
        """
        from bedrock_iac_agent.models import Environment, ResourceType

        parser = _make_parser(model_id)
        context = _make_context()

        result = parser.parse(
            "Create a t3.medium EC2 instance for production",
            context,
        )

        assert result.resource_type == ResourceType.EC2_INSTANCE, (
            f"[{model_label}] Expected EC2_INSTANCE, got {result.resource_type}"
        )
        assert result.environment == Environment.PRODUCTION, (
            f"[{model_label}] Expected PRODUCTION, got {result.environment}"
        )

    @pytest.mark.parametrize("model_label,model_id", INTEGRATION_MODELS)
    def test_parse_lambda_request_with_model(self, model_label: str, model_id: str) -> None:
        """
        Each economic model should correctly parse a Lambda function request.

        **Validates: Requirement 2.1** – agent uses economic Bedrock models.
        """
        from bedrock_iac_agent.models import Environment, ResourceType

        parser = _make_parser(model_id)
        context = _make_context()

        result = parser.parse(
            "Deploy a Python 3.11 Lambda function named data-processor for staging",
            context,
        )

        assert result.resource_type == ResourceType.LAMBDA_FUNCTION, (
            f"[{model_label}] Expected LAMBDA_FUNCTION, got {result.resource_type}"
        )
        assert result.environment == Environment.STAGING, (
            f"[{model_label}] Expected STAGING, got {result.environment}"
        )

    # ------------------------------------------------------------------
    # Consistent output format across models
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("model_label,model_id", INTEGRATION_MODELS)
    def test_output_format_consistent_across_models(
        self, model_label: str, model_id: str
    ) -> None:
        """
        All economic models should return a StructuredRequest with the same
        required fields populated.

        **Validates: Requirement 2.1** – consistent output regardless of model.
        """
        from bedrock_iac_agent.models import StructuredRequest

        parser = _make_parser(model_id)
        context = _make_context()

        result = parser.parse(
            "Create an S3 bucket for development",
            context,
        )

        # Verify the return type
        assert isinstance(result, StructuredRequest), (
            f"[{model_label}] parse() must return a StructuredRequest"
        )

        # Verify all required fields are present and correctly typed
        assert isinstance(result.request_id, str) and len(result.request_id) > 0, (
            f"[{model_label}] request_id must be a non-empty string"
        )
        assert isinstance(result.parameters, dict), (
            f"[{model_label}] parameters must be a dict"
        )
        assert isinstance(result.confidence, float), (
            f"[{model_label}] confidence must be a float"
        )
        assert 0.0 <= result.confidence <= 1.0, (
            f"[{model_label}] confidence must be in [0.0, 1.0], got {result.confidence}"
        )
        assert isinstance(result.user_justification, str), (
            f"[{model_label}] user_justification must be a string"
        )
        assert result.timestamp is not None, (
            f"[{model_label}] timestamp must not be None"
        )

    # ------------------------------------------------------------------
    # Token consumption and cost measurement
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("model_label,model_id", INTEGRATION_MODELS)
    def test_token_consumption_is_logged(
        self,
        model_label: str,
        model_id: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """
        Token usage should be logged for every model invocation.

        **Validates: Requirement 2.3** – agent logs model used and tokens consumed.
        """
        parser = _make_parser(model_id)
        context = _make_context()

        with caplog.at_level(logging.INFO, logger="bedrock_iac_agent.natural_language_parser"):
            parser.parse(
                "I need an S3 bucket for development",
                context,
            )

        # At least one log record should mention token usage
        token_logs = [
            r for r in caplog.records
            if "tokens" in r.getMessage().lower() or "model" in r.getMessage().lower()
        ]
        assert len(token_logs) > 0, (
            f"[{model_label}] Expected token/model usage to be logged, but no matching log records found"
        )

    @pytest.mark.parametrize("model_label,model_id", INTEGRATION_MODELS)
    def test_token_consumption_is_reasonable(
        self, model_label: str, model_id: str
    ) -> None:
        """
        Token consumption for a simple request should be within a reasonable range.
        This guards against runaway prompts or unexpected model behaviour.

        **Validates: Requirement 2.3** – tokens consumed are tracked per interaction.
        """
        from bedrock_iac_agent.natural_language_parser import NaturalLanguageParser

        parser = _make_parser(model_id)
        context = _make_context()

        # Capture token usage by monkey-patching _call_bedrock_with_fallback
        token_usage_captured: Dict[str, int] = {}
        original_call = parser._call_bedrock_with_fallback

        def _capturing_call(messages):  # type: ignore[no-untyped-def]
            result = original_call(messages)
            token_usage_captured.update(result[2])
            return result

        parser._call_bedrock_with_fallback = _capturing_call  # type: ignore[method-assign]

        parser.parse("Create an S3 bucket for development", context)

        assert "input_tokens" in token_usage_captured, (
            f"[{model_label}] input_tokens not captured"
        )
        assert "output_tokens" in token_usage_captured, (
            f"[{model_label}] output_tokens not captured"
        )

        total_tokens = (
            token_usage_captured["input_tokens"] + token_usage_captured["output_tokens"]
        )
        # Sanity bounds: at least 1 token, at most 10 000 for a simple request
        assert total_tokens > 0, (
            f"[{model_label}] Expected > 0 tokens, got {total_tokens}"
        )
        assert total_tokens < 10_000, (
            f"[{model_label}] Unexpectedly high token count: {total_tokens}"
        )

    # ------------------------------------------------------------------
    # Model selection (Requirement 2.2)
    # ------------------------------------------------------------------

    def test_auto_select_picks_cheapest_available_model(self) -> None:
        """
        auto_select=True should pick the cheapest model that is accessible.

        **Validates: Requirement 2.2** – agent selects model with best cost-performance.
        """
        from bedrock_iac_agent.natural_language_parser import (
            ECONOMIC_MODELS,
            NaturalLanguageParser,
        )

        parser = NaturalLanguageParser(auto_select=True)
        selected = parser.get_selected_model()

        assert selected in ECONOMIC_MODELS, (
            f"auto_select should pick a model from ECONOMIC_MODELS, got: {selected}"
        )

    def test_get_selected_model_returns_configured_model(self) -> None:
        """
        get_selected_model() should return the model ID the parser was configured with.

        **Validates: Requirement 2.3** – model used is accessible for auditing.
        """
        model_id = "anthropic.claude-3-haiku-20240307-v1:0"
        parser = _make_parser(model_id)
        assert parser.get_selected_model() == model_id

    # ------------------------------------------------------------------
    # Haiku-specific tests (primary economic model)
    # ------------------------------------------------------------------

    def test_haiku_parses_all_resource_types(self) -> None:
        """
        The Haiku model (primary economic model) should handle all 12 resource types.

        **Validates: Requirement 2.1** – primary economic model is functional.
        """
        from bedrock_iac_agent.models import ResourceType

        model_id = "anthropic.claude-3-haiku-20240307-v1:0"
        parser = _make_parser(model_id)

        test_cases = [
            ("I need an S3 bucket for dev", ResourceType.S3_BUCKET),
            ("Create an EC2 instance for production", ResourceType.EC2_INSTANCE),
            ("Set up a PostgreSQL RDS database for staging", ResourceType.RDS_DATABASE),
            ("Deploy a Lambda function for dev", ResourceType.LAMBDA_FUNCTION),
            ("I need an API Gateway for production", ResourceType.API_GATEWAY),
            ("Create a DynamoDB table for staging", ResourceType.DYNAMODB_TABLE),
            ("Set up a VPC for development", ResourceType.VPC),
            ("Create a security group for production", ResourceType.SECURITY_GROUP),
            ("I need an IAM role for staging", ResourceType.IAM_ROLE),
            ("Create a CloudWatch log group for dev", ResourceType.CLOUDWATCH_LOG_GROUP),
            ("Set up an SNS topic for production", ResourceType.SNS_TOPIC),
            ("Create an SQS queue for staging", ResourceType.SQS_QUEUE),
        ]

        failures: List[str] = []
        for user_input, expected_type in test_cases:
            context = _make_context()
            try:
                result = parser.parse(user_input, context)
                if result.resource_type != expected_type:
                    failures.append(
                        f"Input: '{user_input}' → expected {expected_type.value}, "
                        f"got {result.resource_type}"
                    )
            except Exception as exc:  # noqa: BLE001
                failures.append(f"Input: '{user_input}' → raised {type(exc).__name__}: {exc}")
            # Small delay to avoid throttling
            time.sleep(0.5)

        assert not failures, "Some resource types were not parsed correctly:\n" + "\n".join(failures)

    # ------------------------------------------------------------------
    # Cross-model consistency
    # ------------------------------------------------------------------

    def test_all_models_agree_on_clear_request(self) -> None:
        """
        All economic models should agree on the resource type and environment
        for an unambiguous request.

        **Validates: Requirements 2.1, 2.2** – consistent behaviour across models.
        """
        from bedrock_iac_agent.models import Environment, ResourceType

        user_input = "Create an S3 bucket for development"
        results: Dict[str, Any] = {}

        for model_label, model_id in INTEGRATION_MODELS:
            try:
                parser = _make_parser(model_id)
                context = _make_context()
                result = parser.parse(user_input, context)
                results[model_label] = {
                    "resource_type": result.resource_type,
                    "environment": result.environment,
                }
            except Exception as exc:  # noqa: BLE001
                pytest.skip(f"Model {model_label} ({model_id}) not accessible: {exc}")
            time.sleep(0.3)

        # All models that responded should agree
        resource_types = {v["resource_type"] for v in results.values()}
        environments = {v["environment"] for v in results.values()}

        assert resource_types == {ResourceType.S3_BUCKET}, (
            f"Models disagree on resource type: {results}"
        )
        assert environments == {Environment.DEVELOPMENT}, (
            f"Models disagree on environment: {results}"
        )

    # ------------------------------------------------------------------
    # Ambiguity handling
    # ------------------------------------------------------------------

    def test_haiku_returns_low_confidence_for_ambiguous_request(self) -> None:
        """
        The Haiku model should return low confidence for an ambiguous request.

        **Validates: Requirement 2.1** – model correctly signals uncertainty.
        """
        model_id = "anthropic.claude-3-haiku-20240307-v1:0"
        parser = _make_parser(model_id)
        context = _make_context()

        result = parser.parse("I need some infrastructure", context)

        # Ambiguous request should yield low confidence
        assert result.confidence < 0.7, (
            f"Expected confidence < 0.7 for ambiguous request, got {result.confidence}"
        )
