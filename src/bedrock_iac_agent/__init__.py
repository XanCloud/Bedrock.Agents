"""Bedrock IaC Agent - Conversational AI for AWS Infrastructure Deployment."""

__version__ = "0.1.0"

from .models import (
    ResourceType,
    Environment,
    TechnologyType,
    StructuredRequest,
    Parameter,
    ModuleSchema,
    ModuleInfo,
    TfvarsContent,
    PullRequestDetails,
    PullRequest,
    ConversationContext,
    AgentResponse,
    ValidationResult,
    GitHubCredentials,
    NamingConventions,
    ErrorResponse,
    FileChange,
)

from .interfaces import IConfigurationGenerator, IModuleInventory
from .golden_modules_inventory import GoldenModulesInventory
from .audit_logger import AuditLogger
from .natural_language_parser import NaturalLanguageParser
from .configuration_generator import ConfigurationGenerator
from .agent import BedrockIaCAgent
from .cli import CLIInterface
from .config_manager import (
    AgentConfig,
    BedrockConfig,
    ConfigurationError,
    ConfigurationManager,
    GitHubConfig,
    NamingConfig,
)
from .errors import (
    AgentError,
    AuthenticationError,
    NetworkError,
    ValidationError,
    RepositoryError,
    BedrockError,
    GenerationError,
)

__all__ = [
    "ResourceType",
    "Environment",
    "TechnologyType",
    "StructuredRequest",
    "Parameter",
    "ModuleSchema",
    "ModuleInfo",
    "TfvarsContent",
    "PullRequestDetails",
    "PullRequest",
    "ConversationContext",
    "AgentResponse",
    "ValidationResult",
    "GitHubCredentials",
    "NamingConventions",
    "ErrorResponse",
    "FileChange",
    "GoldenModulesInventory",
    "IConfigurationGenerator",
    "IModuleInventory",
    "AuditLogger",
    "NaturalLanguageParser",
    "ConfigurationGenerator",
    "BedrockIaCAgent",
    "CLIInterface",
    "AgentConfig",
    "BedrockConfig",
    "ConfigurationError",
    "ConfigurationManager",
    "GitHubConfig",
    "NamingConfig",
    "AgentError",
    "AuthenticationError",
    "NetworkError",
    "ValidationError",
    "RepositoryError",
    "BedrockError",
    "GenerationError",
]
