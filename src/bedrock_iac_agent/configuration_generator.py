"""Configuration Generator component for generating Terraform tfvars files."""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .errors import GenerationError, ValidationError
from .interfaces import IConfigurationGenerator
from .models import (
    ConfigContent,
    Environment,
    ModuleSchema,
    NamingConventions,
    Parameter,
    ResourceType,
    StructuredRequest,
    TfvarsContent,
    ValidationResult,
)
from .golden_modules_inventory import GoldenModulesInventory

logger = logging.getLogger(__name__)


class ConfigurationGenerator(IConfigurationGenerator):
    """
    Generates valid Terraform tfvars files using Golden Modules.

    This component takes a StructuredRequest (parsed from natural language) and
    a GoldenModule schema, then produces HCL-formatted tfvars content with:
    - Naming conventions applied
    - Security parameters preserved (cannot be overridden by user)
    - Explanatory comments for human reviewers
    - Validated parameters against the module schema
    """

    # Default naming conventions used when none are provided
    DEFAULT_NAMING_CONVENTIONS = NamingConventions(
        prefix="",
        environment_suffix=True,
        separator="-",
        max_length=63,
        allowed_characters=r"[a-z0-9\-]",
    )

    def __init__(self, audit_logger: Optional[Any] = None) -> None:
        """
        Initialize the ConfigurationGenerator.

        Args:
            audit_logger: Optional AuditLogger instance for structured error logging.
                          If None, errors are only logged via the standard logger.
        """
        self.audit_logger = audit_logger

    def generate_configuration(
        self,
        structured_request: StructuredRequest,
        golden_module: ModuleSchema,
        naming_conventions: Optional[NamingConventions] = None,
    ) -> ConfigContent:
        """
        Generate configuration file content from a StructuredRequest and Golden Module schema.

        The generation pipeline:
        1. Validate requested parameters against the module schema
        2. Apply naming conventions to resource names
        3. Merge user parameters with secure defaults
        4. Preserve security parameters (override any user-supplied values)
        5. Format as HCL and add explanatory comments

        Args:
            structured_request: Parsed user request with resource type, parameters,
                                 and target environment.
            golden_module: The ModuleSchema for the requested resource type.
            naming_conventions: Optional naming conventions to apply. Uses defaults
                                 if not provided.

        Returns:
            ConfigContent with HCL-formatted content and metadata.

        Raises:
            ValueError: If the resource type in the request does not match the
                        golden module's resource type.
            ValidationError: If required parameters are missing or invalid (Req 12.3).
            GenerationError: If HCL generation fails unexpectedly.
        """
        if structured_request.resource_type != golden_module.resource_type:
            mismatch_msg = (
                f"Resource type mismatch: request has "
                f"{structured_request.resource_type}, "
                f"but golden module is for {golden_module.resource_type}"
            )
            raise ValueError(mismatch_msg)

        conventions = naming_conventions or self.DEFAULT_NAMING_CONVENTIONS

        try:
            # Step 1: Validate parameters (collect warnings/errors but continue)
            validation = self.validate_parameters(structured_request.parameters, golden_module)
            if not validation.is_valid:
                # Requirement 12.3: indicate which parameters are invalid and why
                invalid_params = [
                    e.split("'")[1] for e in validation.errors if "'" in e
                ]
                error_details = "; ".join(validation.errors)
                validation_error = ValidationError(
                    message=(
                        f"Invalid parameters for {golden_module.resource_type.value}: "
                        f"{error_details}"
                    ),
                    invalid_parameters=invalid_params,
                    technical_details=error_details,
                    suggested_actions=[
                        "Review the parameter values and correct any invalid entries.",
                        f"Consult the {golden_module.resource_type.value} module documentation "
                        "for valid parameter formats.",
                    ],
                )
                # Requirement 12.5: log the error for later diagnosis
                if self.audit_logger is not None:
                    self.audit_logger.log_error(
                        validation_error,
                        {
                            "operation": "generate_tfvars",
                            "resource_type": golden_module.resource_type.value,
                            "request_id": structured_request.request_id,
                            "invalid_parameters": invalid_params,
                        },
                        error_code="INVALID_PARAMS",
                    )
                for error in validation.errors:
                    logger.warning("Parameter validation error: %s", error)
                raise validation_error

            # Step 2: Build the final parameter set
            final_params: Dict[str, Any] = {}

            # Start with defaults from optional parameters
            for param in golden_module.optional_parameters:
                if param.default is not None:
                    final_params[param.name] = param.default

            # Apply user-supplied parameters (excluding security parameters)
            security_param_names = {p.name for p in golden_module.security_parameters}
            for key, value in structured_request.parameters.items():
                if key in security_param_names:
                    logger.warning(
                        "Security parameter '%s' cannot be overridden by user. "
                        "Preserving Golden Module default value.",
                        key,
                    )
                else:
                    final_params[key] = value

            # Step 3: Apply naming conventions to name-like parameters
            name_keys = self._detect_name_keys(golden_module)
            for key in name_keys:
                if key in final_params:
                    final_params[key] = self.apply_naming_conventions(
                        str(final_params[key]),
                        structured_request.environment,
                        conventions,
                    )

            # Always set / overwrite the environment parameter
            final_params["environment"] = structured_request.environment.value

            # Step 4: Enforce security parameters (always use Golden Module defaults)
            for param in golden_module.security_parameters:
                if param.default is not None:
                    final_params[param.name] = param.default
                elif param.required:
                    # Security parameter is required but has no default — skip with warning
                    logger.warning(
                        "Security parameter '%s' is required but has no default value "
                        "in the Golden Module schema.",
                        param.name,
                    )

            # Step 5: Generate HCL content with comments
            raw_hcl = self._format_hcl(final_params, golden_module)
            commented_hcl = self.add_comments(
                raw_hcl,
                structured_request=structured_request,
                golden_module=golden_module,
                validation=validation,
            )

            file_path = self._build_file_path(structured_request.environment, golden_module)

            return ConfigContent(
                content=commented_hcl,
                file_path=file_path,
                environment=structured_request.environment,
                resource_type=structured_request.resource_type,
                generated_at=datetime.now(timezone.utc),
            )

        except (ValidationError, ValueError):
            # Re-raise validation and value errors as-is
            raise
        except Exception as exc:
            # Wrap unexpected errors in GenerationError (Requirement 12.5)
            gen_error = GenerationError(
                message=(
                    f"Failed to generate configuration for "
                    f"{golden_module.resource_type.value}: {exc}. "
                    "Please review the requested parameters and try again."
                ),
                technical_details=str(exc),
                suggested_actions=[
                    "Review the requested parameters for correctness.",
                    "Ensure all required parameters are provided.",
                    f"Check the {golden_module.resource_type.value} module schema "
                    "for valid parameter formats.",
                ],
            )
            if self.audit_logger is not None:
                self.audit_logger.log_error(
                    gen_error,
                    {
                        "operation": "generate_configuration",
                        "resource_type": golden_module.resource_type.value,
                        "request_id": structured_request.request_id,
                    },
                    error_code="GENERATION_ERROR",
                )
            logger.error(
                "Unexpected error generating configuration for %s: %s",
                golden_module.resource_type.value,
                exc,
            )
            raise gen_error from exc

    # Backward-compatible alias for the Terraform-specific name
    generate_tfvars = generate_configuration

    # ------------------------------------------------------------------
    # apply_naming_conventions
    # ------------------------------------------------------------------

    def apply_naming_conventions(
        self,
        resource_name: str,
        environment: Environment,
        conventions: NamingConventions,
    ) -> str:
        """
        Apply project naming conventions to a resource name.

        The resulting name is built as:
            [prefix<sep>]<sanitized_name>[<sep><env>]

        The name is then truncated to max_length and validated against the
        allowed_characters regex.

        Args:
            resource_name: The base resource name supplied by the user.
            environment: The target deployment environment.
            conventions: Naming conventions to apply.

        Returns:
            The formatted resource name.
        """
        sep = conventions.separator
        parts: List[str] = []

        if conventions.prefix:
            parts.append(conventions.prefix)

        # Sanitize the resource name: lowercase, replace spaces/underscores with sep
        sanitized = resource_name.lower()
        sanitized = re.sub(r"[\s_]+", sep, sanitized)
        # Remove characters not matching allowed_characters (keep sep explicitly)
        allowed_pattern = conventions.allowed_characters
        sanitized = re.sub(
            r"[^a-z0-9" + re.escape(sep) + r"]", "", sanitized
        )
        # Collapse multiple consecutive separators
        sanitized = re.sub(re.escape(sep) + r"+", sep, sanitized)
        sanitized = sanitized.strip(sep)

        if sanitized:
            parts.append(sanitized)

        if conventions.environment_suffix:
            parts.append(environment.value)

        name = sep.join(parts)

        # Enforce max length
        if len(name) > conventions.max_length:
            name = name[: conventions.max_length].rstrip(sep)

        return name

    # ------------------------------------------------------------------
    # validate_parameters
    # ------------------------------------------------------------------

    def validate_parameters(
        self,
        parameters: Dict[str, Any],
        golden_module: ModuleSchema,
    ) -> ValidationResult:
        """
        Validate user-supplied parameters against the Golden Module schema.

        Checks:
        - All required (non-security) parameters are present
        - Parameter types match the schema definition
        - Security parameter overrides are flagged as warnings

        Args:
            parameters: User-supplied parameter dictionary.
            golden_module: The module schema to validate against.

        Returns:
            ValidationResult with is_valid flag, errors, and warnings.
        """
        errors: List[str] = []
        warnings: List[str] = []

        security_param_names = {p.name for p in golden_module.security_parameters}

        # Check required parameters are present
        for param in golden_module.required_parameters:
            if param.name not in parameters and param.name != "environment":
                errors.append(
                    f"Required parameter '{param.name}' is missing. "
                    f"Description: {param.description}"
                )

        # Check type compatibility for supplied parameters
        all_schema_params: Dict[str, Parameter] = {}
        for p in (
            golden_module.required_parameters
            + golden_module.optional_parameters
            + golden_module.security_parameters
        ):
            all_schema_params[p.name] = p

        for key, value in parameters.items():
            if key == "environment":
                continue  # environment is always set by the generator

            if key in security_param_names:
                warnings.append(
                    f"Security parameter '{key}' cannot be overridden. "
                    "The Golden Module default value will be used."
                )
                continue

            if key not in all_schema_params:
                warnings.append(
                    f"Parameter '{key}' is not defined in the Golden Module schema "
                    "and will be ignored."
                )
                continue

            schema_param = all_schema_params[key]
            type_error = self._check_type(key, value, schema_param.type)
            if type_error:
                errors.append(type_error)

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # add_comments
    # ------------------------------------------------------------------

    def add_comments(
        self,
        tfvars_content: str,
        structured_request: Optional[StructuredRequest] = None,
        golden_module: Optional[ModuleSchema] = None,
        validation: Optional[ValidationResult] = None,
    ) -> str:
        """
        Add explanatory comments to tfvars content for human reviewers.

        A header block is prepended with:
        - Generation timestamp and request ID
        - Resource type and environment
        - Module path and version
        - Validation warnings (if any)
        - User justification

        Args:
            tfvars_content: Raw HCL-formatted tfvars string.
            structured_request: Optional request metadata for the header.
            golden_module: Optional module schema for module info in the header.
            validation: Optional validation result to include warnings.

        Returns:
            tfvars content with a comment header prepended.
        """
        lines: List[str] = []
        lines.append("# =============================================================================")
        lines.append("# Generated by Bedrock IaC Agent")
        lines.append("# DO NOT EDIT the security parameters — they are enforced by the Golden Module.")
        lines.append("# =============================================================================")

        if structured_request is not None:
            lines.append(f"# Request ID  : {structured_request.request_id}")
            lines.append(
                f"# Generated at: {structured_request.timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )
            lines.append(f"# Resource    : {structured_request.resource_type.value}")
            lines.append(f"# Environment : {structured_request.environment.value}")
            if structured_request.user_justification:
                lines.append(f"# Justification: {structured_request.user_justification}")

        if golden_module is not None:
            lines.append(f"# Module path : {golden_module.module_path}")
            lines.append(f"# Module ver  : {golden_module.version}")

        if validation is not None and validation.warnings:
            lines.append("#")
            lines.append("# Warnings:")
            for warning in validation.warnings:
                lines.append(f"#   - {warning}")

        lines.append("# =============================================================================")
        lines.append("")

        header = "\n".join(lines)
        return header + tfvars_content

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _format_hcl(
        self,
        parameters: Dict[str, Any],
        golden_module: ModuleSchema,
    ) -> str:
        """
        Format a parameter dictionary as HCL tfvars content.

        HCL formatting rules:
        - Strings: key = "value"
        - Booleans: key = true / key = false  (lowercase)
        - Numbers: key = 42
        - Lists: key = ["a", "b"]
        - Maps: key = { k = "v" }

        Security parameters are grouped at the bottom with a comment.

        Args:
            parameters: Final merged parameter dictionary.
            golden_module: Module schema used to annotate security parameters.

        Returns:
            HCL-formatted string.
        """
        security_param_names = {p.name for p in golden_module.security_parameters}

        # Build a lookup for descriptions
        all_params: Dict[str, Parameter] = {}
        for p in (
            golden_module.required_parameters
            + golden_module.optional_parameters
            + golden_module.security_parameters
        ):
            all_params[p.name] = p

        regular_lines: List[str] = []
        security_lines: List[str] = []

        for key, value in sorted(parameters.items()):
            hcl_value = self._to_hcl_value(value)
            description = all_params[key].description if key in all_params else ""
            comment = f"  # {description}" if description else ""
            line = f"{key} = {hcl_value}{comment}"

            if key in security_param_names:
                security_lines.append(line)
            else:
                regular_lines.append(line)

        parts: List[str] = []
        if regular_lines:
            parts.extend(regular_lines)

        if security_lines:
            parts.append("")
            parts.append("# --- Security parameters (managed by Golden Module) ---")
            parts.extend(security_lines)

        return "\n".join(parts) + "\n"

    def _to_hcl_value(self, value: Any) -> str:
        """
        Convert a Python value to its HCL representation.

        Args:
            value: Python value to convert.

        Returns:
            HCL-formatted string representation.
        """
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            items = ", ".join(f'"{item}"' if isinstance(item, str) else str(item) for item in value)
            return f"[{items}]"
        if isinstance(value, dict):
            if not value:
                return "{}"
            inner = ", ".join(
                f'{k} = "{v}"' if isinstance(v, str) else f"{k} = {v}"
                for k, v in value.items()
            )
            return "{ " + inner + " }"
        # Strings — handle values that look like HCL booleans/numbers already
        str_value = str(value)
        if str_value.lower() in ("true", "false"):
            return str_value.lower()
        # Try to detect numeric strings
        try:
            int(str_value)
            return str_value
        except ValueError:
            pass
        try:
            float(str_value)
            return str_value
        except ValueError:
            pass
        # Default: quoted string
        return f'"{str_value}"'

    def _check_type(self, name: str, value: Any, expected_type: str) -> Optional[str]:
        """
        Check whether a value is compatible with the expected HCL type.

        Args:
            name: Parameter name (for error messages).
            value: The value to check.
            expected_type: Expected HCL type string (string, number, bool, list, map).

        Returns:
            An error message string if the type is incompatible, else None.
        """
        if expected_type == "string":
            if not isinstance(value, str):
                return (
                    f"Parameter '{name}' expects type 'string' "
                    f"but got {type(value).__name__!r}."
                )
        elif expected_type == "number":
            if not isinstance(value, (int, float)):
                # Allow numeric strings
                try:
                    float(str(value))
                except ValueError:
                    return (
                        f"Parameter '{name}' expects type 'number' "
                        f"but got non-numeric value {value!r}."
                    )
        elif expected_type == "bool":
            if not isinstance(value, bool):
                if str(value).lower() not in ("true", "false"):
                    return (
                        f"Parameter '{name}' expects type 'bool' "
                        f"but got {value!r}."
                    )
        elif expected_type == "list":
            if not isinstance(value, list):
                return (
                    f"Parameter '{name}' expects type 'list' "
                    f"but got {type(value).__name__!r}."
                )
        elif expected_type == "map":
            if not isinstance(value, dict):
                return (
                    f"Parameter '{name}' expects type 'map' "
                    f"but got {type(value).__name__!r}."
                )
        return None

    def _detect_name_keys(self, golden_module: ModuleSchema) -> List[str]:
        """
        Detect parameter keys that represent resource names.

        Heuristic: any required or optional parameter whose name ends with
        '_name' or equals 'name' is treated as a name parameter.

        Args:
            golden_module: The module schema to inspect.

        Returns:
            List of parameter names that represent resource names.
        """
        name_keys: List[str] = []
        for param in golden_module.required_parameters + golden_module.optional_parameters:
            if param.name == "name" or param.name.endswith("_name"):
                name_keys.append(param.name)
        return name_keys

    def _build_file_path(
        self,
        environment: Environment,
        golden_module: ModuleSchema,
    ) -> str:
        """
        Build the relative file path for the generated tfvars file.

        Convention: environments/{env}/{resource_type}/terraform.tfvars

        Args:
            environment: Target deployment environment.
            golden_module: Module schema (provides resource type).

        Returns:
            Relative file path string.
        """
        return (
            f"environments/{environment.value}/"
            f"{golden_module.resource_type.value}/terraform.tfvars"
        )
