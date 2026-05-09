"""Core data models for the Bedrock IaC Agent."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime


class TechnologyType(Enum):
    """IaC technology types supported by the agent.

    This enum enables the agent to be extended to support additional
    infrastructure-as-code technologies beyond Terraform (Requirement 15.3).
    """

    TERRAFORM = "terraform"
    KUBERNETES = "kubernetes"


class ResourceType(Enum):
    """AWS resource types supported by Golden Modules."""
    S3_BUCKET = "s3_bucket"
    EC2_INSTANCE = "ec2_instance"
    RDS_DATABASE = "rds_database"
    LAMBDA_FUNCTION = "lambda_function"
    API_GATEWAY = "api_gateway"
    DYNAMODB_TABLE = "dynamodb_table"
    VPC = "vpc"
    SECURITY_GROUP = "security_group"
    IAM_ROLE = "iam_role"
    CLOUDWATCH_LOG_GROUP = "cloudwatch_log_group"
    SNS_TOPIC = "sns_topic"
    SQS_QUEUE = "sqs_queue"


class Environment(Enum):
    """Deployment environments."""
    DEVELOPMENT = "dev"
    STAGING = "staging"
    PRODUCTION = "prod"


@dataclass
class StructuredRequest:
    """Parsed representation of user request.

    This model is technology-agnostic: the ``technology_type`` field identifies
    which IaC technology (Terraform, Kubernetes, …) the request targets, so the
    same NLP parser can feed different configuration generators without any
    Terraform-specific logic leaking into the parsing layer (Requirement 15.3).
    """

    resource_type: ResourceType
    parameters: Dict[str, Any]
    environment: Environment
    confidence: float  # 0.0-1.0, from NLP parsing
    user_justification: str
    request_id: str
    timestamp: datetime
    technology_type: TechnologyType = field(default=TechnologyType.TERRAFORM)
    """IaC technology this request targets. Defaults to Terraform for backward compatibility."""


@dataclass
class Parameter:
    """Parameter definition for Golden Module."""
    name: str
    type: str  # string, number, bool, list, map
    required: bool
    default: Optional[Any]
    description: str
    validation_rules: Optional[Dict[str, Any]] = None
    is_security_parameter: bool = False  # Cannot be overridden by user


@dataclass
class ModuleSchema:
    """Schema for a Golden Module."""
    resource_type: ResourceType
    module_path: str
    required_parameters: List[Parameter]
    optional_parameters: List[Parameter]
    security_parameters: List[Parameter]
    naming_pattern: str  # e.g., "{project}-{env}-{resource}-{suffix}"
    description: str
    version: str


@dataclass
class TfvarsContent:
    """Generated tfvars file content."""
    content: str  # HCL-formatted content
    file_path: str  # Relative path in repository
    environment: Environment
    resource_type: ResourceType
    generated_at: datetime


@dataclass
class PullRequestDetails:
    """Details for creating a Pull Request."""
    title: str
    description: str
    source_branch: str
    target_branch: str  # Usually "main"
    labels: List[str]
    reviewers: List[str]
    metadata: Dict[str, Any]  # Includes request_id, conversation_id


@dataclass
class PullRequest:
    """Created Pull Request information."""
    url: str
    number: int
    branch_name: str
    created_at: datetime


@dataclass
class ConversationContext:
    """Maintains context across conversation turns."""
    session_id: str
    user_id: str
    history: List[Dict[str, str]] = field(default_factory=list)  # List of {role, content} messages
    current_request: Optional[StructuredRequest] = None
    pending_clarifications: List[str] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)  # User preferences (default env, etc.)


@dataclass
class AgentResponse:
    """Response from agent to user."""
    message: str
    pr_url: Optional[str] = None
    status: str = "success"  # success, error, needs_clarification
    next_steps: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of validation operations."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class GitHubCredentials:
    """Credentials for Azure GitHub."""
    token: str
    organization: str
    repository: str


@dataclass
class NamingConventions:
    """Project-specific naming conventions."""
    prefix: str  # e.g., "mycompany"
    environment_suffix: bool
    separator: str  # e.g., "-"
    max_length: int
    allowed_characters: str  # regex pattern


@dataclass
class ErrorResponse:
    """Structured error response for user-facing error reporting.

    Attributes:
        error_code: Machine-readable error code (e.g. "AUTH_FAILED", "INVALID_PARAMS").
        error_message: User-friendly description of the error.
        technical_details: Technical details for logging and debugging.
        suggested_actions: List of actions the user can take to resolve the error.
        retry_possible: Whether the operation can be retried automatically.
    """

    error_code: str  # e.g., "AUTH_FAILED", "INVALID_PARAMS"
    error_message: str  # User-friendly message
    technical_details: str = ""  # For logging/debugging
    suggested_actions: List[str] = field(default_factory=list)  # What user can do
    retry_possible: bool = False


@dataclass
class ModuleInfo:
    """Information about an available Golden Module."""
    resource_type: ResourceType
    name: str
    description: str
    version: str


@dataclass
class FileChange:
    """Represents a file change for Git operations."""
    file_path: str
    content: str
    operation: str  # "add", "modify", "delete"
