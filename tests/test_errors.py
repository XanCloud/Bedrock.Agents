"""Unit tests for custom exception classes and ErrorResponse integration.

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5
"""

import pytest

from bedrock_iac_agent.errors import (
    AgentError,
    AuthenticationError,
    BedrockError,
    GenerationError,
    NetworkError,
    RepositoryError,
    RetryStrategy,
    ThrottlingError,
    ValidationError,
)
from bedrock_iac_agent.models import ErrorResponse


# ---------------------------------------------------------------------------
# AgentError (base class)
# ---------------------------------------------------------------------------


class TestAgentError:
    def test_basic_instantiation(self) -> None:
        err = AgentError(
            message="Something went wrong",
            error_code="GENERIC_ERROR",
        )
        assert str(err) == "Something went wrong"
        assert err.error_code == "GENERIC_ERROR"
        assert err.error_message == "Something went wrong"
        assert err.technical_details == ""
        assert err.suggested_actions == []
        assert err.retry_possible is False

    def test_full_instantiation(self) -> None:
        err = AgentError(
            message="Detailed error",
            error_code="DETAIL_ERROR",
            technical_details="Stack trace here",
            suggested_actions=["Do this", "Do that"],
            retry_possible=True,
        )
        assert err.technical_details == "Stack trace here"
        assert err.suggested_actions == ["Do this", "Do that"]
        assert err.retry_possible is True

    def test_to_error_response_returns_dataclass(self) -> None:
        err = AgentError(
            message="msg",
            error_code="CODE",
            technical_details="details",
            suggested_actions=["action1"],
            retry_possible=True,
        )
        response = err.to_error_response()
        assert isinstance(response, ErrorResponse)
        assert response.error_code == "CODE"
        assert response.error_message == "msg"
        assert response.technical_details == "details"
        assert response.suggested_actions == ["action1"]
        assert response.retry_possible is True

    def test_is_exception_subclass(self) -> None:
        err = AgentError(message="x", error_code="X")
        assert isinstance(err, Exception)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(AgentError) as exc_info:
            raise AgentError(message="raised", error_code="RAISED")
        assert exc_info.value.error_code == "RAISED"


# ---------------------------------------------------------------------------
# AuthenticationError
# ---------------------------------------------------------------------------


class TestAuthenticationError:
    def test_default_error_code(self) -> None:
        err = AuthenticationError()
        assert err.error_code == "AUTH_FAILED"

    def test_default_message(self) -> None:
        err = AuthenticationError()
        assert "Authentication failed" in str(err)

    def test_retry_not_possible(self) -> None:
        err = AuthenticationError()
        assert err.retry_possible is False

    def test_default_suggested_actions_not_empty(self) -> None:
        err = AuthenticationError()
        assert len(err.suggested_actions) > 0

    def test_custom_message_and_details(self) -> None:
        err = AuthenticationError(
            message="Token expired",
            technical_details="401 Unauthorized",
        )
        assert str(err) == "Token expired"
        assert err.technical_details == "401 Unauthorized"

    def test_custom_suggested_actions(self) -> None:
        err = AuthenticationError(suggested_actions=["Custom action"])
        assert err.suggested_actions == ["Custom action"]

    def test_is_agent_error_subclass(self) -> None:
        assert issubclass(AuthenticationError, AgentError)

    def test_to_error_response(self) -> None:
        err = AuthenticationError(message="Bad token")
        response = err.to_error_response()
        assert response.error_code == "AUTH_FAILED"
        assert response.retry_possible is False

    def test_can_be_caught_as_agent_error(self) -> None:
        with pytest.raises(AgentError):
            raise AuthenticationError()


# ---------------------------------------------------------------------------
# NetworkError
# ---------------------------------------------------------------------------


class TestNetworkError:
    def test_default_error_code(self) -> None:
        err = NetworkError()
        assert err.error_code == "NETWORK_ERROR"

    def test_retry_is_possible(self) -> None:
        """Network errors should be retryable (Requirement 12.2)."""
        err = NetworkError()
        assert err.retry_possible is True

    def test_default_suggested_actions_not_empty(self) -> None:
        err = NetworkError()
        assert len(err.suggested_actions) > 0

    def test_custom_message(self) -> None:
        err = NetworkError(message="Connection timed out")
        assert str(err) == "Connection timed out"

    def test_is_agent_error_subclass(self) -> None:
        assert issubclass(NetworkError, AgentError)

    def test_to_error_response(self) -> None:
        err = NetworkError()
        response = err.to_error_response()
        assert response.error_code == "NETWORK_ERROR"
        assert response.retry_possible is True


# ---------------------------------------------------------------------------
# ValidationError
# ---------------------------------------------------------------------------


class TestValidationError:
    def test_default_error_code(self) -> None:
        err = ValidationError()
        assert err.error_code == "INVALID_PARAMS"

    def test_retry_not_possible(self) -> None:
        err = ValidationError()
        assert err.retry_possible is False

    def test_invalid_parameters_default_empty(self) -> None:
        err = ValidationError()
        assert err.invalid_parameters == []

    def test_invalid_parameters_stored(self) -> None:
        err = ValidationError(invalid_parameters=["bucket_name", "region"])
        assert "bucket_name" in err.invalid_parameters
        assert "region" in err.invalid_parameters

    def test_custom_message_with_invalid_params(self) -> None:
        err = ValidationError(
            message="Parameter 'bucket_name' is required",
            invalid_parameters=["bucket_name"],
        )
        assert "bucket_name" in str(err)
        assert err.invalid_parameters == ["bucket_name"]

    def test_is_agent_error_subclass(self) -> None:
        assert issubclass(ValidationError, AgentError)

    def test_to_error_response(self) -> None:
        err = ValidationError(message="Bad params")
        response = err.to_error_response()
        assert response.error_code == "INVALID_PARAMS"
        assert response.retry_possible is False


# ---------------------------------------------------------------------------
# RepositoryError
# ---------------------------------------------------------------------------


class TestRepositoryError:
    def test_default_error_code(self) -> None:
        err = RepositoryError()
        assert err.error_code == "REPO_ERROR"

    def test_retry_not_possible(self) -> None:
        err = RepositoryError()
        assert err.retry_possible is False

    def test_default_suggested_actions_mention_permissions(self) -> None:
        err = RepositoryError()
        combined = " ".join(err.suggested_actions).lower()
        assert "permission" in combined or "access" in combined

    def test_custom_message(self) -> None:
        err = RepositoryError(message="Branch already exists")
        assert str(err) == "Branch already exists"

    def test_is_agent_error_subclass(self) -> None:
        assert issubclass(RepositoryError, AgentError)

    def test_to_error_response(self) -> None:
        err = RepositoryError()
        response = err.to_error_response()
        assert response.error_code == "REPO_ERROR"


# ---------------------------------------------------------------------------
# BedrockError
# ---------------------------------------------------------------------------


class TestBedrockError:
    def test_default_error_code(self) -> None:
        err = BedrockError()
        assert err.error_code == "BEDROCK_ERROR"

    def test_retry_possible_by_default(self) -> None:
        err = BedrockError()
        assert err.retry_possible is True

    def test_retry_can_be_disabled(self) -> None:
        err = BedrockError(retry_possible=False)
        assert err.retry_possible is False

    def test_default_suggested_actions_not_empty(self) -> None:
        err = BedrockError()
        assert len(err.suggested_actions) > 0

    def test_custom_message(self) -> None:
        err = BedrockError(message="Model throttled")
        assert str(err) == "Model throttled"

    def test_is_agent_error_subclass(self) -> None:
        assert issubclass(BedrockError, AgentError)

    def test_to_error_response(self) -> None:
        err = BedrockError()
        response = err.to_error_response()
        assert response.error_code == "BEDROCK_ERROR"
        assert response.retry_possible is True


# ---------------------------------------------------------------------------
# GenerationError
# ---------------------------------------------------------------------------


class TestGenerationError:
    def test_default_error_code(self) -> None:
        err = GenerationError()
        assert err.error_code == "GENERATION_ERROR"

    def test_retry_not_possible(self) -> None:
        err = GenerationError()
        assert err.retry_possible is False

    def test_default_suggested_actions_not_empty(self) -> None:
        err = GenerationError()
        assert len(err.suggested_actions) > 0

    def test_custom_message(self) -> None:
        err = GenerationError(message="Invalid HCL syntax")
        assert str(err) == "Invalid HCL syntax"

    def test_is_agent_error_subclass(self) -> None:
        assert issubclass(GenerationError, AgentError)

    def test_to_error_response(self) -> None:
        err = GenerationError()
        response = err.to_error_response()
        assert response.error_code == "GENERATION_ERROR"
        assert response.retry_possible is False


# ---------------------------------------------------------------------------
# Cross-cutting: all errors produce valid ErrorResponse
# ---------------------------------------------------------------------------


class TestErrorResponseIntegration:
    @pytest.mark.parametrize(
        "exc_class",
        [
            AuthenticationError,
            NetworkError,
            ValidationError,
            RepositoryError,
            BedrockError,
            GenerationError,
        ],
    )
    def test_all_errors_produce_error_response(self, exc_class: type) -> None:
        err = exc_class()
        response = err.to_error_response()
        assert isinstance(response, ErrorResponse)
        assert response.error_code != ""
        assert response.error_message != ""
        assert isinstance(response.suggested_actions, list)
        assert isinstance(response.retry_possible, bool)

    @pytest.mark.parametrize(
        "exc_class",
        [
            AuthenticationError,
            NetworkError,
            ValidationError,
            RepositoryError,
            BedrockError,
            GenerationError,
        ],
    )
    def test_all_errors_are_agent_error_subclasses(self, exc_class: type) -> None:
        assert issubclass(exc_class, AgentError)

    def test_network_error_is_retryable_auth_is_not(self) -> None:
        """Verify retry semantics are correct for key error types."""
        assert NetworkError().retry_possible is True
        assert AuthenticationError().retry_possible is False
        assert ValidationError().retry_possible is False
        assert RepositoryError().retry_possible is False
        assert GenerationError().retry_possible is False


# ---------------------------------------------------------------------------
# RetryStrategy  (Requirement 12.2)
# ---------------------------------------------------------------------------


class TestRetryStrategy:
    """Tests for the RetryStrategy class.

    Requirement 12.2: Retry network operations up to 3 times with exponential backoff.
    """

    # ------------------------------------------------------------------
    # should_retry() – max attempts boundary
    # ------------------------------------------------------------------

    def test_should_retry_returns_false_when_max_attempts_reached(self) -> None:
        """should_retry() must return False once attempt equals max_attempts."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(NetworkError(), attempt=3) is False

    def test_should_retry_returns_false_when_attempt_exceeds_max(self) -> None:
        """should_retry() must return False when attempt exceeds max_attempts."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(NetworkError(), attempt=5) is False

    def test_should_retry_returns_true_on_last_valid_attempt(self) -> None:
        """should_retry() returns True when attempt is still below max_attempts."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(NetworkError(), attempt=2) is True

    # ------------------------------------------------------------------
    # should_retry() – retryable error types
    # ------------------------------------------------------------------

    def test_should_retry_network_error_within_attempts(self) -> None:
        """NetworkError is retryable (Requirement 12.2)."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(NetworkError("connection reset"), attempt=1) is True

    def test_should_retry_throttling_error_within_attempts(self) -> None:
        """ThrottlingError is retryable (Requirement 12.2)."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(ThrottlingError("rate limited"), attempt=1) is True

    def test_should_retry_network_error_on_second_attempt(self) -> None:
        """NetworkError is still retryable on the second attempt."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(NetworkError(), attempt=2) is True

    def test_should_retry_throttling_error_on_second_attempt(self) -> None:
        """ThrottlingError is still retryable on the second attempt."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(ThrottlingError(), attempt=2) is True

    # ------------------------------------------------------------------
    # should_retry() – non-retryable error types
    # ------------------------------------------------------------------

    def test_should_not_retry_authentication_error(self) -> None:
        """AuthenticationError is not retryable."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(AuthenticationError(), attempt=1) is False

    def test_should_not_retry_validation_error(self) -> None:
        """ValidationError is not retryable."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(ValidationError(), attempt=1) is False

    def test_should_not_retry_generic_exception(self) -> None:
        """A plain Exception is not retryable."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(Exception("unexpected"), attempt=1) is False

    def test_should_not_retry_value_error(self) -> None:
        """ValueError is not retryable."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(ValueError("bad input"), attempt=1) is False

    # ------------------------------------------------------------------
    # get_delay() – exponential backoff values
    # ------------------------------------------------------------------

    def test_get_delay_attempt_zero(self) -> None:
        """get_delay(0) == base_delay * exponential_base^0 == base_delay."""
        strategy = RetryStrategy(base_delay=1.0, max_delay=10.0, exponential_base=2.0)
        assert strategy.get_delay(0) == 1.0

    def test_get_delay_attempt_one(self) -> None:
        """get_delay(1) == base_delay * exponential_base^1."""
        strategy = RetryStrategy(base_delay=1.0, max_delay=10.0, exponential_base=2.0)
        assert strategy.get_delay(1) == 2.0

    def test_get_delay_attempt_two(self) -> None:
        """get_delay(2) == base_delay * exponential_base^2."""
        strategy = RetryStrategy(base_delay=1.0, max_delay=10.0, exponential_base=2.0)
        assert strategy.get_delay(2) == 4.0

    def test_get_delay_custom_base_delay(self) -> None:
        """get_delay() respects a custom base_delay."""
        strategy = RetryStrategy(base_delay=0.5, max_delay=10.0, exponential_base=2.0)
        assert strategy.get_delay(1) == 1.0  # 0.5 * 2^1

    # ------------------------------------------------------------------
    # get_delay() – max_delay cap
    # ------------------------------------------------------------------

    def test_get_delay_capped_at_max_delay(self) -> None:
        """get_delay() must not exceed max_delay."""
        strategy = RetryStrategy(base_delay=1.0, max_delay=3.0, exponential_base=2.0)
        assert strategy.get_delay(10) == 3.0

    def test_get_delay_exactly_at_max_delay(self) -> None:
        """get_delay() returns max_delay when computed value equals max_delay."""
        strategy = RetryStrategy(base_delay=1.0, max_delay=4.0, exponential_base=2.0)
        # 1.0 * 2^2 == 4.0 == max_delay
        assert strategy.get_delay(2) == 4.0

    def test_get_delay_just_below_max_delay(self) -> None:
        """get_delay() returns the computed value when it is below max_delay."""
        strategy = RetryStrategy(base_delay=1.0, max_delay=10.0, exponential_base=2.0)
        # 1.0 * 2^3 == 8.0 < 10.0
        assert strategy.get_delay(3) == 8.0

    # ------------------------------------------------------------------
    # Default configuration
    # ------------------------------------------------------------------

    def test_default_max_attempts_is_three(self) -> None:
        """Default max_attempts must be 3 (Requirement 12.2)."""
        strategy = RetryStrategy()
        assert strategy.max_attempts == 3

    def test_default_base_delay(self) -> None:
        """Default base_delay must be 1.0 second."""
        strategy = RetryStrategy()
        assert strategy.base_delay == 1.0

    def test_default_max_delay(self) -> None:
        """Default max_delay must be 10.0 seconds."""
        strategy = RetryStrategy()
        assert strategy.max_delay == 10.0

    def test_default_exponential_base(self) -> None:
        """Default exponential_base must be 2.0."""
        strategy = RetryStrategy()
        assert strategy.exponential_base == 2.0


# ---------------------------------------------------------------------------
# Task 9.4: Error handling unit tests
# Requirements: 12.1, 12.2, 12.3, 12.4, 12.5
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Requirement 12.1 – Authentication error handling
# ---------------------------------------------------------------------------


class TestAuthenticationErrorHandling:
    """Verify AuthenticationError carries credential-verification guidance.

    Requirement 12.1: When a GitHub authentication error occurs, the agent
    must inform the user and request credential verification.
    """

    def test_suggested_actions_mention_token_verification(self) -> None:
        """Default suggested actions must guide the user to verify their token."""
        err = AuthenticationError()
        combined = " ".join(err.suggested_actions).lower()
        assert "token" in combined or "credential" in combined

    def test_suggested_actions_mention_permissions(self) -> None:
        """Default suggested actions must mention repository permissions."""
        err = AuthenticationError()
        combined = " ".join(err.suggested_actions).lower()
        assert "permission" in combined or "access" in combined or "scope" in combined

    def test_error_response_suggested_actions_preserved(self) -> None:
        """to_error_response() must carry the same suggested actions."""
        err = AuthenticationError()
        response = err.to_error_response()
        assert response.suggested_actions == err.suggested_actions

    def test_error_response_not_retryable(self) -> None:
        """Authentication errors must not be retried (Requirement 12.1)."""
        err = AuthenticationError()
        response = err.to_error_response()
        assert response.retry_possible is False

    def test_custom_message_preserved_in_error_response(self) -> None:
        """A custom message is reflected in the ErrorResponse."""
        err = AuthenticationError(
            message="GitHub token has expired",
            technical_details="HTTP 401 Unauthorized",
        )
        response = err.to_error_response()
        assert response.error_message == "GitHub token has expired"
        assert response.technical_details == "HTTP 401 Unauthorized"

    def test_authentication_error_is_not_retried_by_retry_strategy(self) -> None:
        """RetryStrategy must not retry AuthenticationError (Requirement 12.1)."""
        strategy = RetryStrategy(max_attempts=3)
        err = AuthenticationError()
        # Even on the first attempt, auth errors should not be retried
        assert strategy.should_retry(err, attempt=1) is False

    def test_authentication_error_raised_and_caught_as_agent_error(self) -> None:
        """AuthenticationError can be caught as AgentError for uniform handling."""
        with pytest.raises(AgentError) as exc_info:
            raise AuthenticationError(message="Bad credentials")
        assert exc_info.value.error_code == "AUTH_FAILED"


# ---------------------------------------------------------------------------
# Requirement 12.2 – Network error retry logic
# ---------------------------------------------------------------------------


class TestNetworkErrorRetryLogic:
    """Verify retry behaviour for NetworkError and ThrottlingError.

    Requirement 12.2: Retry network operations up to 3 times with
    exponential backoff before failing.
    """

    def test_retry_strategy_retries_network_error_up_to_max_attempts(self) -> None:
        """should_retry() returns True for attempts 1 and 2 (below max=3)."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(NetworkError(), attempt=1) is True
        assert strategy.should_retry(NetworkError(), attempt=2) is True

    def test_retry_strategy_stops_at_max_attempts(self) -> None:
        """should_retry() returns False once attempt reaches max_attempts."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(NetworkError(), attempt=3) is False

    def test_retry_strategy_retries_throttling_error(self) -> None:
        """ThrottlingError is also retryable (Requirement 12.2)."""
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(ThrottlingError(), attempt=1) is True
        assert strategy.should_retry(ThrottlingError(), attempt=2) is True
        assert strategy.should_retry(ThrottlingError(), attempt=3) is False

    def test_retry_loop_calls_operation_three_times_on_persistent_failure(self) -> None:
        """A persistent NetworkError causes exactly max_attempts calls."""
        strategy = RetryStrategy(max_attempts=3, base_delay=0.0, max_delay=0.0)
        call_count = 0

        def failing_operation() -> None:
            nonlocal call_count
            call_count += 1
            raise NetworkError("connection refused")

        with pytest.raises(NetworkError):
            last_exc = None
            for attempt in range(strategy.max_attempts):
                try:
                    failing_operation()
                    break
                except Exception as exc:
                    last_exc = exc
                    if not strategy.should_retry(exc, attempt + 1):
                        raise
            else:
                raise last_exc  # type: ignore[misc]

        assert call_count == 3

    def test_retry_loop_succeeds_on_second_attempt(self) -> None:
        """Operation succeeds on the second attempt after one transient failure."""
        strategy = RetryStrategy(max_attempts=3, base_delay=0.0, max_delay=0.0)
        call_count = 0

        def flaky_operation() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise NetworkError("transient failure")
            return "success"

        result = None
        last_exc = None
        for attempt in range(strategy.max_attempts):
            try:
                result = flaky_operation()
                break
            except Exception as exc:
                last_exc = exc
                if not strategy.should_retry(exc, attempt + 1):
                    raise

        assert result == "success"
        assert call_count == 2

    def test_exponential_backoff_delays_increase_between_retries(self) -> None:
        """Delays grow exponentially: 1s, 2s, 4s (capped at max_delay)."""
        strategy = RetryStrategy(
            max_attempts=3, base_delay=1.0, max_delay=10.0, exponential_base=2.0
        )
        delay_0 = strategy.get_delay(0)
        delay_1 = strategy.get_delay(1)
        delay_2 = strategy.get_delay(2)

        assert delay_0 < delay_1 < delay_2
        assert delay_0 == 1.0
        assert delay_1 == 2.0
        assert delay_2 == 4.0

    def test_exponential_backoff_capped_at_max_delay(self) -> None:
        """Delay never exceeds max_delay regardless of attempt number."""
        strategy = RetryStrategy(
            max_attempts=3, base_delay=1.0, max_delay=5.0, exponential_base=2.0
        )
        for attempt in range(10):
            assert strategy.get_delay(attempt) <= 5.0

    def test_network_error_is_retryable_flag(self) -> None:
        """NetworkError.retry_possible must be True (Requirement 12.2)."""
        err = NetworkError()
        assert err.retry_possible is True

    def test_network_error_response_is_retryable(self) -> None:
        """ErrorResponse from NetworkError must have retry_possible=True."""
        err = NetworkError()
        response = err.to_error_response()
        assert response.retry_possible is True

    def test_non_network_errors_are_not_retried(self) -> None:
        """Only NetworkError and ThrottlingError are retried; others are not."""
        strategy = RetryStrategy(max_attempts=3)
        non_retryable = [
            AuthenticationError(),
            ValidationError(),
            RepositoryError(),
            ValueError("unexpected"),
            RuntimeError("crash"),
        ]
        for err in non_retryable:
            assert strategy.should_retry(err, attempt=1) is False, (
                f"Expected {type(err).__name__} to not be retried"
            )


# ---------------------------------------------------------------------------
# Requirement 12.3 – Validation error messages
# ---------------------------------------------------------------------------


class TestValidationErrorMessages:
    """Verify ValidationError carries actionable parameter information.

    Requirement 12.3: When tfvars generation fails due to invalid parameters,
    the agent must indicate which parameters are invalid and why.
    """

    def test_invalid_parameters_list_is_accessible(self) -> None:
        """invalid_parameters attribute stores the list of bad parameter names."""
        err = ValidationError(invalid_parameters=["bucket_name", "region", "tags"])
        assert err.invalid_parameters == ["bucket_name", "region", "tags"]

    def test_invalid_parameters_empty_by_default(self) -> None:
        """When no invalid_parameters are given, the list is empty."""
        err = ValidationError()
        assert err.invalid_parameters == []

    def test_message_can_reference_invalid_parameter(self) -> None:
        """A descriptive message can name the offending parameter."""
        err = ValidationError(
            message="Parameter 'instance_type' has an invalid value: 't99.xlarge'",
            invalid_parameters=["instance_type"],
        )
        assert "instance_type" in str(err)
        assert err.invalid_parameters == ["instance_type"]

    def test_suggested_actions_guide_user_to_fix_parameters(self) -> None:
        """Default suggested actions must guide the user to correct parameters."""
        err = ValidationError()
        combined = " ".join(err.suggested_actions).lower()
        assert "parameter" in combined or "value" in combined or "review" in combined

    def test_error_response_preserves_error_code(self) -> None:
        """to_error_response() must use the INVALID_PARAMS error code."""
        err = ValidationError()
        response = err.to_error_response()
        assert response.error_code == "INVALID_PARAMS"

    def test_error_response_not_retryable(self) -> None:
        """Validation errors are not retryable (user must fix the input)."""
        err = ValidationError()
        response = err.to_error_response()
        assert response.retry_possible is False

    def test_multiple_invalid_parameters_all_stored(self) -> None:
        """All invalid parameter names are stored, not just the first."""
        params = ["bucket_name", "versioning", "encryption", "region"]
        err = ValidationError(invalid_parameters=params)
        for param in params:
            assert param in err.invalid_parameters

    def test_validation_error_not_retried_by_retry_strategy(self) -> None:
        """RetryStrategy must not retry ValidationError (Requirement 12.3)."""
        strategy = RetryStrategy(max_attempts=3)
        err = ValidationError(invalid_parameters=["bucket_name"])
        assert strategy.should_retry(err, attempt=1) is False

    def test_technical_details_can_explain_why_parameter_is_invalid(self) -> None:
        """technical_details field can carry the reason for the validation failure."""
        err = ValidationError(
            message="Invalid parameters detected",
            technical_details="'instance_type' must be one of: t3.micro, t3.small, t3.medium",
            invalid_parameters=["instance_type"],
        )
        assert "instance_type" in err.technical_details
        response = err.to_error_response()
        assert "instance_type" in response.technical_details


# ---------------------------------------------------------------------------
# Requirement 12.4 – Repository error handling
# ---------------------------------------------------------------------------


class TestRepositoryErrorHandling:
    """Verify RepositoryError carries actionable repository guidance.

    Requirement 12.4: When the base repository is not accessible, the agent
    must inform the user and suggest verifying permissions.
    """

    def test_suggested_actions_mention_permissions(self) -> None:
        """Default suggested actions must mention permissions or access."""
        err = RepositoryError()
        combined = " ".join(err.suggested_actions).lower()
        assert "permission" in combined or "access" in combined

    def test_suggested_actions_mention_repository(self) -> None:
        """Default suggested actions must reference the repository."""
        err = RepositoryError()
        combined = " ".join(err.suggested_actions).lower()
        assert "repository" in combined or "repo" in combined or "branch" in combined

    def test_error_response_error_code(self) -> None:
        """to_error_response() must use the REPO_ERROR error code."""
        err = RepositoryError()
        response = err.to_error_response()
        assert response.error_code == "REPO_ERROR"

    def test_error_response_not_retryable(self) -> None:
        """Repository errors are not automatically retried."""
        err = RepositoryError()
        response = err.to_error_response()
        assert response.retry_possible is False

    def test_custom_message_for_branch_already_exists(self) -> None:
        """A specific message can describe the branch-already-exists scenario."""
        err = RepositoryError(
            message="Branch 'iac-agent/s3-bucket/dev/20240115' already exists",
            technical_details="git error: branch already exists",
        )
        assert "already exists" in str(err)
        assert err.error_code == "REPO_ERROR"

    def test_repository_error_not_retried_by_retry_strategy(self) -> None:
        """RetryStrategy must not retry RepositoryError."""
        strategy = RetryStrategy(max_attempts=3)
        err = RepositoryError()
        assert strategy.should_retry(err, attempt=1) is False


# ---------------------------------------------------------------------------
# Requirement 12.5 – Error logging
# ---------------------------------------------------------------------------


import json
import logging
from io import StringIO

from bedrock_iac_agent.audit_logger import AuditLogger, JSONFormatter


class TestErrorLogging:
    """Verify that errors are logged with full context for diagnostics.

    Requirement 12.5: All errors must be recorded in logs for later diagnosis.
    """

    @pytest.fixture
    def logger_with_capture(self):
        """Return an AuditLogger and a StringIO stream capturing its output."""
        audit_logger = AuditLogger(logger_name="test_error_logging")
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(JSONFormatter())
        audit_logger.logger.addHandler(handler)
        return audit_logger, log_stream

    def _last_log(self, stream: StringIO) -> dict:
        """Parse the last JSON log line from the stream."""
        lines = stream.getvalue().strip().split("\n")
        return json.loads(lines[-1])

    def test_log_error_records_authentication_error(
        self, logger_with_capture
    ) -> None:
        """AuthenticationError is logged with AUTH_FAILED code (Requirement 12.1)."""
        audit_logger, log_stream = logger_with_capture
        err = AuthenticationError(message="Token expired")
        audit_logger.log_error(err, {"operation": "authenticate"}, error_code="AUTH_FAILED")

        log_data = self._last_log(log_stream)
        assert log_data["event_type"] == "error"
        assert log_data["error_code"] == "AUTH_FAILED"
        assert log_data["status"] == "error"
        assert "Token expired" in log_data["message"]

    def test_log_error_records_network_error(self, logger_with_capture) -> None:
        """NetworkError is logged with NETWORK_ERROR code (Requirement 12.2)."""
        audit_logger, log_stream = logger_with_capture
        err = NetworkError(message="Connection timed out")
        audit_logger.log_error(err, {"operation": "push_branch"}, error_code="NETWORK_ERROR")

        log_data = self._last_log(log_stream)
        assert log_data["error_code"] == "NETWORK_ERROR"
        assert "Connection timed out" in log_data["message"]

    def test_log_error_records_validation_error(self, logger_with_capture) -> None:
        """ValidationError is logged with INVALID_PARAMS code (Requirement 12.3)."""
        audit_logger, log_stream = logger_with_capture
        err = ValidationError(
            message="Parameter 'bucket_name' is required",
            invalid_parameters=["bucket_name"],
        )
        audit_logger.log_error(err, {"operation": "generate_tfvars"}, error_code="INVALID_PARAMS")

        log_data = self._last_log(log_stream)
        assert log_data["error_code"] == "INVALID_PARAMS"
        assert "bucket_name" in log_data["message"]

    def test_log_error_records_repository_error(self, logger_with_capture) -> None:
        """RepositoryError is logged with REPO_ERROR code (Requirement 12.4)."""
        audit_logger, log_stream = logger_with_capture
        err = RepositoryError(message="Branch already exists")
        audit_logger.log_error(err, {"operation": "create_branch"}, error_code="REPO_ERROR")

        log_data = self._last_log(log_stream)
        assert log_data["error_code"] == "REPO_ERROR"
        assert "Branch already exists" in log_data["message"]

    def test_log_error_includes_stack_trace(self, logger_with_capture) -> None:
        """Error log must include a stack trace for diagnostics (Requirement 12.5)."""
        audit_logger, log_stream = logger_with_capture
        try:
            raise NetworkError("simulated network failure")
        except NetworkError as err:
            audit_logger.log_error(err, {"operation": "clone_repository"})

        log_data = self._last_log(log_stream)
        assert "stack_trace" in log_data
        assert "NetworkError" in log_data["stack_trace"]
        assert "simulated network failure" in log_data["stack_trace"]

    def test_log_error_includes_request_context(self, logger_with_capture) -> None:
        """Error log must include request context fields for traceability."""
        audit_logger, log_stream = logger_with_capture
        err = ValidationError(message="Invalid params")
        context = {
            "user_id": "dev@example.com",
            "request_id": "req-abc-123",
            "resource_type": "s3_bucket",
            "environment": "dev",
        }
        audit_logger.log_error(err, context, error_code="INVALID_PARAMS")

        log_data = self._last_log(log_stream)
        assert log_data["user_id"] == "dev@example.com"
        assert log_data["request_id"] == "req-abc-123"
        assert log_data["resource_type"] == "s3_bucket"
        assert log_data["environment"] == "dev"

    def test_log_error_uses_exception_class_name_as_default_code(
        self, logger_with_capture
    ) -> None:
        """When no error_code is given, the exception class name is used."""
        audit_logger, log_stream = logger_with_capture
        err = AuthenticationError(message="Bad token")
        audit_logger.log_error(err, {})  # no explicit error_code

        log_data = self._last_log(log_stream)
        assert log_data["error_code"] == "AuthenticationError"

    def test_log_error_output_is_valid_json(self, logger_with_capture) -> None:
        """Each error log entry must be valid JSON (Requirement 12.5)."""
        audit_logger, log_stream = logger_with_capture
        err = NetworkError(message="Timeout")
        audit_logger.log_error(err, {"operation": "push"})

        raw = log_stream.getvalue().strip()
        # Should not raise
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_log_error_level_is_error(self, logger_with_capture) -> None:
        """Error log entries must use ERROR level."""
        audit_logger, log_stream = logger_with_capture
        err = RepositoryError(message="Access denied")
        audit_logger.log_error(err, {})

        log_data = self._last_log(log_stream)
        assert log_data["level"] == "ERROR"

    def test_log_error_called_on_github_authentication_failure(self) -> None:
        """GitHubIntegration.authenticate() calls log_error on failure (Req 12.1, 12.5)."""
        from unittest.mock import MagicMock, patch
        from bedrock_iac_agent.github_integration import GitHubIntegration
        from bedrock_iac_agent.models import GitHubCredentials

        credentials = GitHubCredentials(
            token="bad_token", organization="org", repository="repo"
        )
        mock_audit_logger = MagicMock(spec=AuditLogger)
        integration = GitHubIntegration(
            credentials=credentials,
            audit_logger=mock_audit_logger,
            retry_strategy=RetryStrategy(max_attempts=1, base_delay=0.0),
        )

        with patch("bedrock_iac_agent.github_integration.Github") as mock_github_cls:
            from github import GithubException
            mock_client = MagicMock()
            mock_client.get_user.side_effect = GithubException(
                401, {"message": "Bad credentials"}, None
            )
            mock_github_cls.return_value = mock_client

            with pytest.raises(AuthenticationError):
                integration.authenticate()

        mock_audit_logger.log_error.assert_called_once()
        call_kwargs = mock_audit_logger.log_error.call_args
        logged_error = call_kwargs[0][0]
        assert isinstance(logged_error, AuthenticationError)

    def test_log_error_called_on_network_failure_during_push(self) -> None:
        """GitHubIntegration._do_push() calls log_error on network failure (Req 12.2, 12.5)."""
        from unittest.mock import MagicMock
        import git as gitlib
        from bedrock_iac_agent.github_integration import GitHubIntegration
        from bedrock_iac_agent.models import GitHubCredentials

        credentials = GitHubCredentials(
            token="token", organization="org", repository="repo"
        )
        mock_audit_logger = MagicMock(spec=AuditLogger)
        # Use max_attempts=1 so the retry loop doesn't mask the log_error call count
        integration = GitHubIntegration(
            credentials=credentials,
            audit_logger=mock_audit_logger,
            retry_strategy=RetryStrategy(max_attempts=1, base_delay=0.0),
        )

        mock_repo = MagicMock()
        mock_branch = MagicMock()
        mock_branch.name = "iac-agent/s3-bucket/dev/20240115-103000"
        mock_origin = MagicMock()
        mock_origin.push.side_effect = gitlib.GitCommandError("push", 128)
        mock_repo.remote.return_value = mock_origin

        with pytest.raises(NetworkError):
            integration.push_branch(mock_repo, mock_branch)

        mock_audit_logger.log_error.assert_called_once()
        call_args = mock_audit_logger.log_error.call_args
        logged_error = call_args[0][0]
        assert isinstance(logged_error, NetworkError)
