"""Error classes and retry strategy for the Bedrock IaC Agent.

Defines custom exceptions and the RetryStrategy used across all components
for resilient handling of transient failures.

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base exception
# ---------------------------------------------------------------------------


class AgentError(Exception):
    """Base exception for all Bedrock IaC Agent errors.

    All custom exceptions carry structured metadata so they can be converted
    to an :class:`~bedrock_iac_agent.models.ErrorResponse` for user-facing
    reporting.

    Args:
        message: Human-readable description of the error.
        error_code: Machine-readable error code (e.g. ``"AUTH_FAILED"``).
        technical_details: Technical details for logging/debugging.
        suggested_actions: List of corrective actions the user can take.
        retry_possible: Whether the operation can be retried automatically.
    """

    #: Default error code used when no specific code is provided.
    default_error_code: str = "AGENT_ERROR"
    #: Default human-readable message.
    default_message: str = "An unexpected error occurred."
    #: Default retry behaviour.
    default_retry_possible: bool = False
    #: Default suggested actions.
    default_suggested_actions: List[str] = []

    def __init__(
        self,
        message: Optional[str] = None,
        error_code: Optional[str] = None,
        technical_details: str = "",
        suggested_actions: Optional[List[str]] = None,
        retry_possible: Optional[bool] = None,
    ) -> None:
        self.error_message: str = message or self.default_message
        self.error_code: str = error_code or self.default_error_code
        self.technical_details: str = technical_details
        self.suggested_actions: List[str] = (
            suggested_actions
            if suggested_actions is not None
            else list(self.default_suggested_actions)
        )
        self.retry_possible: bool = (
            retry_possible
            if retry_possible is not None
            else self.default_retry_possible
        )
        super().__init__(self.error_message)

    def to_error_response(self) -> "ErrorResponseType":
        """Convert this exception to an :class:`~bedrock_iac_agent.models.ErrorResponse`.

        Returns:
            An ``ErrorResponse`` dataclass populated from this exception's fields.
        """
        # Import here to avoid circular imports
        from bedrock_iac_agent.models import ErrorResponse

        return ErrorResponse(
            error_code=self.error_code,
            error_message=self.error_message,
            technical_details=self.technical_details,
            suggested_actions=list(self.suggested_actions),
            retry_possible=self.retry_possible,
        )


# Type alias used in annotations only
ErrorResponseType = object  # resolved at runtime via the import inside to_error_response


# Alias for backwards compatibility
BedrockIaCAgentError = AgentError


# ---------------------------------------------------------------------------
# Authentication errors  (Requirement 12.1)
# ---------------------------------------------------------------------------


class AuthenticationError(AgentError):
    """Raised when authentication with GitHub or AWS fails.

    Requirement 12.1: Inform user and request credential verification.
    """

    default_error_code = "AUTH_FAILED"
    default_message = "Authentication failed. Please verify your credentials."
    default_retry_possible = False
    default_suggested_actions = [
        "Verify that your GitHub token is valid and has not expired.",
        "Ensure the token has the required repository permissions.",
        "Re-generate the token and update your configuration.",
    ]


# ---------------------------------------------------------------------------
# Network errors  (Requirement 12.2)
# ---------------------------------------------------------------------------


class NetworkError(AgentError):
    """Raised when a network operation fails (clone, push, API call, etc.).

    Requirement 12.2: Retry up to 3 times with exponential backoff before failing.
    """

    default_error_code = "NETWORK_ERROR"
    default_message = "A network error occurred. The operation will be retried."
    default_retry_possible = True
    default_suggested_actions = [
        "Check your internet connection.",
        "Verify that the GitHub API is reachable.",
        "The operation will be retried automatically up to 3 times.",
    ]


# ---------------------------------------------------------------------------
# Throttling errors
# ---------------------------------------------------------------------------


class ThrottlingError(AgentError):
    """Raised when a service throttles requests.

    Examples: Bedrock model throttling, GitHub API rate limiting.
    Retryable with exponential backoff (Requirement 12.2).
    """

    default_error_code = "THROTTLING_ERROR"
    default_message = "The request was throttled. Retrying with backoff."
    default_retry_possible = True
    default_suggested_actions = [
        "Wait a moment before retrying.",
        "Consider reducing the frequency of requests.",
    ]


# ---------------------------------------------------------------------------
# Bedrock errors
# ---------------------------------------------------------------------------


class BedrockError(AgentError):
    """Raised when an AWS Bedrock operation fails.

    Examples: model throttling, invalid model response, token limit exceeded.
    """

    default_error_code = "BEDROCK_ERROR"
    default_message = "A Bedrock model error occurred."
    default_retry_possible = True
    default_suggested_actions = [
        "Retry the request — transient throttling may resolve automatically.",
        "Try rephrasing your request to reduce token usage.",
        "Consider switching to a different economic model.",
    ]


# ---------------------------------------------------------------------------
# Validation errors  (Requirement 12.3)
# ---------------------------------------------------------------------------


class ValidationError(AgentError):
    """Raised when input validation fails (invalid parameters, unsupported types, etc.).

    Requirement 12.3: Indicate which parameters are invalid and why.

    Args:
        invalid_parameters: List of parameter names that failed validation.
    """

    default_error_code = "INVALID_PARAMS"
    default_message = "One or more parameters are invalid."
    default_retry_possible = False
    default_suggested_actions = [
        "Review the parameter values and correct any invalid entries.",
        "Consult the Golden Module documentation for valid parameter formats.",
    ]

    def __init__(
        self,
        message: Optional[str] = None,
        error_code: Optional[str] = None,
        technical_details: str = "",
        suggested_actions: Optional[List[str]] = None,
        retry_possible: Optional[bool] = None,
        invalid_parameters: Optional[List[str]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            technical_details=technical_details,
            suggested_actions=suggested_actions,
            retry_possible=retry_possible,
        )
        self.invalid_parameters: List[str] = invalid_parameters or []


# ---------------------------------------------------------------------------
# Repository errors  (Requirement 12.4)
# ---------------------------------------------------------------------------


class RepositoryError(AgentError):
    """Raised when a repository operation fails (branch exists, merge conflict, etc.).

    Requirement 12.4: Inform user and suggest verifying permissions.
    """

    default_error_code = "REPO_ERROR"
    default_message = "A repository error occurred."
    default_retry_possible = False
    default_suggested_actions = [
        "Verify that you have the required access permissions to the repository.",
        "Check whether the branch already exists and delete it if necessary.",
        "Ensure the base repository URL is correct.",
    ]


# ---------------------------------------------------------------------------
# Generation / configuration errors
# ---------------------------------------------------------------------------


class GenerationError(AgentError):
    """Raised when configuration generation fails.

    Examples: invalid HCL syntax in generated tfvars, missing required parameters.
    """

    default_error_code = "GENERATION_ERROR"
    default_message = "Failed to generate the configuration file."
    default_retry_possible = False
    default_suggested_actions = [
        "Review the requested parameters for correctness.",
        "Ensure all required parameters are provided.",
        "Check the Golden Module schema for valid parameter formats.",
    ]


# Alias for backwards compatibility
ConfigurationError = GenerationError


# ---------------------------------------------------------------------------
# Module errors
# ---------------------------------------------------------------------------


class ModuleNotFoundError(AgentError):
    """Raised when a requested Golden Module does not exist in the inventory."""

    default_error_code = "MODULE_NOT_FOUND"
    default_message = "The requested Golden Module was not found."
    default_retry_possible = False
    default_suggested_actions = [
        "Check the list of available Golden Modules.",
        "Request a similar supported resource type.",
    ]


# ---------------------------------------------------------------------------
# Retry strategy
# ---------------------------------------------------------------------------


class RetryStrategy:
    """Exponential-backoff retry strategy for network-sensitive operations.

    Determines whether a failed operation should be retried and calculates
    the delay before the next attempt using exponential backoff.

    Per the design document (Requirement 12.2), retries are triggered for
    :class:`NetworkError` and :class:`ThrottlingError` up to *max_attempts*
    times.

    Args:
        max_attempts: Maximum number of total attempts (default: 3).
        base_delay: Initial delay in seconds before the first retry (default: 1.0).
        max_delay: Upper bound on the computed delay in seconds (default: 10.0).
        exponential_base: Base for the exponential calculation (default: 2.0).

    Example::

        strategy = RetryStrategy()

        for attempt in range(strategy.max_attempts):
            try:
                result = do_network_call()
                break
            except Exception as exc:
                if strategy.should_retry(exc, attempt + 1):
                    time.sleep(strategy.get_delay(attempt))
                else:
                    raise
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 10.0,
        exponential_base: float = 2.0,
    ) -> None:
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """Determine whether the failed operation should be retried.

        Args:
            error: The exception that was raised.
            attempt: The attempt number that just failed (1-indexed).

        Returns:
            ``True`` if the operation should be retried, ``False`` otherwise.

        The operation is retried when:
        - *attempt* is less than :attr:`max_attempts`, **and**
        - *error* is an instance of :class:`NetworkError`,
          :class:`ThrottlingError`, or a known transient GitHub/Git exception
          (``github.GithubException``, ``git.GitCommandError``).
        """
        if attempt >= self.max_attempts:
            return False
        if isinstance(error, (NetworkError, ThrottlingError)):
            return True
        # Also retry on transient GitHub API and Git command errors
        try:
            from github import GithubException  # type: ignore[import]
            if isinstance(error, GithubException):
                return True
        except ImportError:
            pass
        try:
            import git  # type: ignore[import]
            if isinstance(error, git.GitCommandError):
                return True
        except ImportError:
            pass
        return False

    def get_delay(self, attempt: int) -> float:
        """Calculate the delay (in seconds) before the next retry attempt.

        Uses exponential backoff: ``base_delay * exponential_base ** attempt``,
        capped at :attr:`max_delay`.

        Args:
            attempt: The zero-indexed attempt number (0 for the first retry).

        Returns:
            Delay in seconds, capped at :attr:`max_delay`.
        """
        delay = self.base_delay * (self.exponential_base ** attempt)
        return min(delay, self.max_delay)
