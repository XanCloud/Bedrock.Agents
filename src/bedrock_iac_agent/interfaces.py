"""Abstract interfaces for extensibility (Requirement 15).

These interfaces define the contracts that configuration generators and module
inventories must satisfy. Concrete implementations exist for Terraform today;
future implementations (e.g. Kubernetes) can be added without changing the
rest of the system.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .models import (
    ConfigContent,
    Environment,
    ModuleInfo,
    ModuleSchema,
    NamingConventions,
    ResourceType,
    StructuredRequest,
    TfvarsContent,
    ValidationResult,
)


class IConfigurationGenerator(ABC):
    """Abstract interface for configuration generators.

    Separates the NLP interpretation layer from the configuration generation
    layer (Requirement 15.2, 15.3), allowing alternative implementations for
    different infrastructure technologies such as Kubernetes.

    Any concrete generator must implement all abstract methods below.
    """

    @abstractmethod
    def generate_configuration(
        self,
        structured_request: StructuredRequest,
        golden_module: ModuleSchema,
        naming_conventions: Optional[NamingConventions] = None,
    ) -> ConfigContent:
        """Generate configuration file content from a StructuredRequest.

        Args:
            structured_request: Parsed user request with resource type,
                                 parameters, and target environment.
            golden_module: The ModuleSchema for the requested resource type.
            naming_conventions: Optional naming conventions to apply.

        Returns:
            ConfigContent with formatted content and metadata.

        Raises:
            ValueError: If the resource type in the request does not match
                        the golden module's resource type.
            ValidationError: If required parameters are missing or invalid.
            GenerationError: If configuration generation fails unexpectedly.
        """

    def generate_tfvars(
        self,
        structured_request: StructuredRequest,
        golden_module: ModuleSchema,
        naming_conventions: Optional[NamingConventions] = None,
    ) -> ConfigContent:
        """Backward-compatible alias for :meth:`generate_configuration`.

        Deprecated: use :meth:`generate_configuration` for new code.
        """
        return self.generate_configuration(
            structured_request, golden_module, naming_conventions
        )

    @abstractmethod
    def apply_naming_conventions(
        self,
        resource_name: str,
        environment: Environment,
        conventions: NamingConventions,
    ) -> str:
        """Apply project naming conventions to a resource name.

        Args:
            resource_name: The base resource name supplied by the user.
            environment: The target deployment environment.
            conventions: Naming conventions to apply.

        Returns:
            The formatted resource name.
        """

    @abstractmethod
    def validate_parameters(
        self,
        parameters: Dict[str, Any],
        golden_module: ModuleSchema,
    ) -> ValidationResult:
        """Validate user-supplied parameters against the module schema.

        Args:
            parameters: User-supplied parameter dictionary.
            golden_module: The module schema to validate against.

        Returns:
            ValidationResult with is_valid flag, errors, and warnings.
        """

    @abstractmethod
    def add_comments(
        self,
        tfvars_content: str,
        structured_request: Optional[StructuredRequest] = None,
        golden_module: Optional[ModuleSchema] = None,
        validation: Optional[ValidationResult] = None,
    ) -> str:
        """Add explanatory comments to configuration content.

        Args:
            tfvars_content: Raw formatted configuration string.
            structured_request: Optional request metadata for the header.
            golden_module: Optional module schema for module info in the header.
            validation: Optional validation result to include warnings.

        Returns:
            Configuration content with a comment header prepended.
        """


class IModuleInventory(ABC):
    """Abstract interface for module inventories.

    Decouples the rest of the system from the specific catalog of available
    modules (Requirement 15.1, 15.2). A Terraform implementation exists today;
    a Kubernetes implementation can be added later without touching the agent
    orchestrator or the configuration generator.
    """

    @abstractmethod
    def get_module(self, resource_type: ResourceType) -> Optional[ModuleInfo]:
        """Retrieve module information by ResourceType.

        Args:
            resource_type: The type of infrastructure resource.

        Returns:
            ModuleInfo if the module exists, None otherwise.
        """

    @abstractmethod
    def list_available_modules(self) -> List[ModuleInfo]:
        """List all available modules in this inventory.

        Returns:
            List of ModuleInfo for all supported modules.
        """

    @abstractmethod
    def get_module_schema(self, resource_type: ResourceType) -> ModuleSchema:
        """Return the parameter schema for a module.

        Args:
            resource_type: The type of infrastructure resource.

        Returns:
            ModuleSchema containing parameter definitions.

        Raises:
            ModuleNotFoundError: If the resource type is not supported.
        """

    @abstractmethod
    def suggest_alternatives(self, resource_type: ResourceType) -> List[ResourceType]:
        """Suggest alternative resource types for unsupported requests.

        Args:
            resource_type: The requested resource type.

        Returns:
            List of alternative ResourceType suggestions.
        """
