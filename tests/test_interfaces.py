"""Tests for abstract interfaces and their implementations.

Validates Requirements 15.1, 15.2, 15.3, 15.4 — extensibility architecture.
"""

import inspect
from abc import ABC
from datetime import datetime
from typing import Optional

import pytest

from src.bedrock_iac_agent import (
    ConfigurationGenerator,
    Environment,
    GoldenModulesInventory,
    IConfigurationGenerator,
    IModuleInventory,
    ModuleInfo,
    ModuleSchema,
    NamingConventions,
    Parameter,
    ResourceType,
    StructuredRequest,
    TechnologyType,
    TfvarsContent,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_request(
    resource_type: ResourceType = ResourceType.S3_BUCKET,
    parameters: dict | None = None,
    environment: Environment = Environment.DEVELOPMENT,
) -> StructuredRequest:
    return StructuredRequest(
        resource_type=resource_type,
        parameters=parameters or {"bucket_name": "test-bucket"},
        environment=environment,
        confidence=0.95,
        user_justification="Test",
        request_id="req-test-001",
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
    )


INVENTORY = GoldenModulesInventory()


# ---------------------------------------------------------------------------
# IConfigurationGenerator interface contract tests
# Validates: Requirements 15.2, 15.3
# ---------------------------------------------------------------------------

class TestIConfigurationGeneratorIsABC:
    """Verify IConfigurationGenerator is a proper abstract base class."""

    def test_is_abstract_base_class(self):
        """IConfigurationGenerator must be an ABC (Req 15.2)."""
        assert issubclass(IConfigurationGenerator, ABC)

    def test_cannot_instantiate_directly(self):
        """Direct instantiation of the interface must raise TypeError (Req 15.2)."""
        with pytest.raises(TypeError):
            IConfigurationGenerator()  # type: ignore[abstract]

    def test_has_generate_tfvars_abstract_method(self):
        """generate_tfvars must be declared as an abstract method."""
        method = getattr(IConfigurationGenerator, "generate_tfvars", None)
        assert method is not None
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_apply_naming_conventions_abstract_method(self):
        """apply_naming_conventions must be declared as an abstract method."""
        method = getattr(IConfigurationGenerator, "apply_naming_conventions", None)
        assert method is not None
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_validate_parameters_abstract_method(self):
        """validate_parameters must be declared as an abstract method."""
        method = getattr(IConfigurationGenerator, "validate_parameters", None)
        assert method is not None
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_add_comments_abstract_method(self):
        """add_comments must be declared as an abstract method."""
        method = getattr(IConfigurationGenerator, "add_comments", None)
        assert method is not None
        assert getattr(method, "__isabstractmethod__", False)

    def test_abstract_methods_set(self):
        """All four abstract methods must be present."""
        abstract_methods = IConfigurationGenerator.__abstractmethods__
        assert "generate_tfvars" in abstract_methods
        assert "apply_naming_conventions" in abstract_methods
        assert "validate_parameters" in abstract_methods
        assert "add_comments" in abstract_methods


class TestConfigurationGeneratorImplementsInterface:
    """Verify ConfigurationGenerator satisfies IConfigurationGenerator (Req 15.2)."""

    def test_is_subclass_of_interface(self):
        """ConfigurationGenerator must be a subclass of IConfigurationGenerator."""
        assert issubclass(ConfigurationGenerator, IConfigurationGenerator)

    def test_can_be_instantiated(self):
        """ConfigurationGenerator must be instantiable (no abstract methods left)."""
        gen = ConfigurationGenerator()
        assert gen is not None

    def test_isinstance_of_interface(self):
        """A ConfigurationGenerator instance must satisfy isinstance check."""
        gen = ConfigurationGenerator()
        assert isinstance(gen, IConfigurationGenerator)

    def test_generate_tfvars_returns_tfvars_content(self):
        """generate_tfvars must return a TfvarsContent instance."""
        gen = ConfigurationGenerator()
        schema = INVENTORY.get_module_schema(ResourceType.S3_BUCKET)
        request = make_request(
            resource_type=ResourceType.S3_BUCKET,
            parameters={"bucket_name": "my-bucket"},
        )
        result = gen.generate_tfvars(request, schema)
        assert isinstance(result, TfvarsContent)

    def test_apply_naming_conventions_returns_string(self):
        """apply_naming_conventions must return a string."""
        gen = ConfigurationGenerator()
        conventions = NamingConventions(
            prefix="myco",
            environment_suffix=True,
            separator="-",
            max_length=63,
            allowed_characters=r"[a-z0-9\-]",
        )
        result = gen.apply_naming_conventions("my-bucket", Environment.DEVELOPMENT, conventions)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_validate_parameters_returns_validation_result(self):
        """validate_parameters must return a ValidationResult."""
        gen = ConfigurationGenerator()
        schema = INVENTORY.get_module_schema(ResourceType.S3_BUCKET)
        result = gen.validate_parameters({"bucket_name": "test"}, schema)
        assert isinstance(result, ValidationResult)
        assert hasattr(result, "is_valid")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")

    def test_add_comments_returns_string(self):
        """add_comments must return a string."""
        gen = ConfigurationGenerator()
        result = gen.add_comments('bucket_name = "test"\n')
        assert isinstance(result, str)
        assert 'bucket_name = "test"' in result


# ---------------------------------------------------------------------------
# IModuleInventory interface contract tests
# Validates: Requirements 15.1, 15.2
# ---------------------------------------------------------------------------

class TestIModuleInventoryIsABC:
    """Verify IModuleInventory is a proper abstract base class."""

    def test_is_abstract_base_class(self):
        """IModuleInventory must be an ABC (Req 15.1)."""
        assert issubclass(IModuleInventory, ABC)

    def test_cannot_instantiate_directly(self):
        """Direct instantiation of the interface must raise TypeError (Req 15.1)."""
        with pytest.raises(TypeError):
            IModuleInventory()  # type: ignore[abstract]

    def test_has_get_module_abstract_method(self):
        """get_module must be declared as an abstract method."""
        method = getattr(IModuleInventory, "get_module", None)
        assert method is not None
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_list_available_modules_abstract_method(self):
        """list_available_modules must be declared as an abstract method."""
        method = getattr(IModuleInventory, "list_available_modules", None)
        assert method is not None
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_get_module_schema_abstract_method(self):
        """get_module_schema must be declared as an abstract method."""
        method = getattr(IModuleInventory, "get_module_schema", None)
        assert method is not None
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_suggest_alternatives_abstract_method(self):
        """suggest_alternatives must be declared as an abstract method."""
        method = getattr(IModuleInventory, "suggest_alternatives", None)
        assert method is not None
        assert getattr(method, "__isabstractmethod__", False)

    def test_abstract_methods_set(self):
        """All four abstract methods must be present."""
        abstract_methods = IModuleInventory.__abstractmethods__
        assert "get_module" in abstract_methods
        assert "list_available_modules" in abstract_methods
        assert "get_module_schema" in abstract_methods
        assert "suggest_alternatives" in abstract_methods


class TestGoldenModulesInventoryImplementsInterface:
    """Verify GoldenModulesInventory satisfies IModuleInventory (Req 15.1)."""

    def test_is_subclass_of_interface(self):
        """GoldenModulesInventory must be a subclass of IModuleInventory."""
        assert issubclass(GoldenModulesInventory, IModuleInventory)

    def test_can_be_instantiated(self):
        """GoldenModulesInventory must be instantiable."""
        inv = GoldenModulesInventory()
        assert inv is not None

    def test_isinstance_of_interface(self):
        """A GoldenModulesInventory instance must satisfy isinstance check."""
        inv = GoldenModulesInventory()
        assert isinstance(inv, IModuleInventory)

    def test_get_module_returns_module_info_or_none(self):
        """get_module must return ModuleInfo or None."""
        inv = GoldenModulesInventory()
        result = inv.get_module(ResourceType.S3_BUCKET)
        assert result is None or isinstance(result, ModuleInfo)

    def test_list_available_modules_returns_list(self):
        """list_available_modules must return a list of ModuleInfo."""
        inv = GoldenModulesInventory()
        result = inv.list_available_modules()
        assert isinstance(result, list)
        assert all(isinstance(m, ModuleInfo) for m in result)

    def test_get_module_schema_returns_module_schema(self):
        """get_module_schema must return a ModuleSchema."""
        inv = GoldenModulesInventory()
        result = inv.get_module_schema(ResourceType.S3_BUCKET)
        assert isinstance(result, ModuleSchema)

    def test_suggest_alternatives_returns_list_of_resource_types(self):
        """suggest_alternatives must return a list of ResourceType."""
        inv = GoldenModulesInventory()
        result = inv.suggest_alternatives(ResourceType.S3_BUCKET)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, ResourceType)


# ---------------------------------------------------------------------------
# Extensibility / substitutability tests
# Validates: Requirements 15.1, 15.2, 15.4
# ---------------------------------------------------------------------------

class TestInterfaceSubstitutability:
    """Verify that concrete implementations can be used wherever the interface is expected.

    This tests the Liskov Substitution Principle — any code that accepts an
    IConfigurationGenerator or IModuleInventory should work with the concrete
    Terraform implementations, and future Kubernetes implementations.
    """

    def test_configuration_generator_usable_as_interface(self):
        """ConfigurationGenerator can be passed as IConfigurationGenerator (Req 15.2)."""
        def use_generator(gen: IConfigurationGenerator, schema: ModuleSchema) -> TfvarsContent:
            request = make_request(
                resource_type=ResourceType.S3_BUCKET,
                parameters={"bucket_name": "test"},
            )
            return gen.generate_tfvars(request, schema)

        gen = ConfigurationGenerator()
        schema = INVENTORY.get_module_schema(ResourceType.S3_BUCKET)
        result = use_generator(gen, schema)
        assert isinstance(result, TfvarsContent)

    def test_golden_modules_inventory_usable_as_interface(self):
        """GoldenModulesInventory can be passed as IModuleInventory (Req 15.1)."""
        def use_inventory(inv: IModuleInventory) -> int:
            return len(inv.list_available_modules())

        inv = GoldenModulesInventory()
        count = use_inventory(inv)
        assert count == 12

    def test_custom_generator_can_implement_interface(self):
        """A custom generator class can implement IConfigurationGenerator (Req 15.2, 15.4)."""

        class MinimalGenerator(IConfigurationGenerator):
            """Minimal concrete implementation for testing extensibility."""

            def generate_tfvars(self, structured_request, golden_module, naming_conventions=None):
                return TfvarsContent(
                    content="# minimal\n",
                    file_path="test.tfvars",
                    environment=structured_request.environment,
                    resource_type=structured_request.resource_type,
                    generated_at=datetime(2024, 1, 1),
                )

            def apply_naming_conventions(self, resource_name, environment, conventions):
                return resource_name

            def validate_parameters(self, parameters, golden_module):
                return ValidationResult(is_valid=True)

            def add_comments(self, tfvars_content, structured_request=None, golden_module=None, validation=None):
                return tfvars_content

        gen = MinimalGenerator()
        assert isinstance(gen, IConfigurationGenerator)

        schema = INVENTORY.get_module_schema(ResourceType.S3_BUCKET)
        request = make_request(parameters={"bucket_name": "test"})
        result = gen.generate_tfvars(request, schema)
        assert isinstance(result, TfvarsContent)

    def test_custom_inventory_can_implement_interface(self):
        """A custom inventory class can implement IModuleInventory (Req 15.1, 15.4)."""

        class MinimalInventory(IModuleInventory):
            """Minimal concrete implementation for testing extensibility."""

            def get_module(self, resource_type):
                return None

            def list_available_modules(self):
                return []

            def get_module_schema(self, resource_type):
                return ModuleSchema(
                    resource_type=resource_type,
                    module_path="test/path",
                    required_parameters=[],
                    optional_parameters=[],
                    security_parameters=[],
                    naming_pattern="{name}",
                    description="Test",
                    version="0.0.1",
                )

            def suggest_alternatives(self, resource_type):
                return []

        inv = MinimalInventory()
        assert isinstance(inv, IModuleInventory)
        assert inv.list_available_modules() == []

    def test_incomplete_generator_cannot_be_instantiated(self):
        """A class that only partially implements IConfigurationGenerator cannot be instantiated."""

        class IncompleteGenerator(IConfigurationGenerator):
            def generate_tfvars(self, structured_request, golden_module, naming_conventions=None):
                return None  # type: ignore[return-value]

            # Missing: apply_naming_conventions, validate_parameters, add_comments

        with pytest.raises(TypeError):
            IncompleteGenerator()  # type: ignore[abstract]

    def test_incomplete_inventory_cannot_be_instantiated(self):
        """A class that only partially implements IModuleInventory cannot be instantiated."""

        class IncompleteInventory(IModuleInventory):
            def get_module(self, resource_type):
                return None

            # Missing: list_available_modules, get_module_schema, suggest_alternatives

        with pytest.raises(TypeError):
            IncompleteInventory()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# NLP / Config separation tests
# Validates: Requirement 15.3
# ---------------------------------------------------------------------------

class TestNLPConfigSeparation:
    """Verify that NLP parsing is separated from configuration generation (Req 15.3)."""

    def test_structured_request_has_technology_type_field(self):
        """StructuredRequest must carry a technology_type field for tech-agnostic routing."""
        request = make_request()
        assert hasattr(request, "technology_type")

    def test_structured_request_defaults_to_terraform(self):
        """StructuredRequest defaults to Terraform for backward compatibility (Req 15.4)."""
        request = make_request()
        assert request.technology_type == TechnologyType.TERRAFORM

    def test_structured_request_can_be_set_to_kubernetes(self):
        """StructuredRequest can represent a Kubernetes request (Req 15.3)."""
        request = StructuredRequest(
            resource_type=ResourceType.S3_BUCKET,
            parameters={"bucket_name": "test"},
            environment=Environment.DEVELOPMENT,
            confidence=0.9,
            user_justification="Test",
            request_id="req-k8s-001",
            timestamp=datetime(2024, 1, 15),
            technology_type=TechnologyType.KUBERNETES,
        )
        assert request.technology_type == TechnologyType.KUBERNETES

    def test_technology_type_enum_has_terraform_and_kubernetes(self):
        """TechnologyType enum must include both TERRAFORM and KUBERNETES values."""
        assert TechnologyType.TERRAFORM.value == "terraform"
        assert TechnologyType.KUBERNETES.value == "kubernetes"

    def test_configuration_generator_does_not_import_nlp_parser(self):
        """ConfigurationGenerator module must not import NaturalLanguageParser (Req 15.3)."""
        import src.bedrock_iac_agent.configuration_generator as cg_module
        source = inspect.getsource(cg_module)
        assert "NaturalLanguageParser" not in source
        assert "natural_language_parser" not in source

    def test_interfaces_module_does_not_import_nlp_parser(self):
        """interfaces.py must not import NaturalLanguageParser (Req 15.3)."""
        import src.bedrock_iac_agent.interfaces as iface_module
        source = inspect.getsource(iface_module)
        assert "NaturalLanguageParser" not in source
        assert "natural_language_parser" not in source


# ---------------------------------------------------------------------------
# Terraform backward compatibility tests
# Validates: Requirement 15.4
# ---------------------------------------------------------------------------

class TestTerraformBackwardCompatibility:
    """Verify existing Terraform functionality is preserved (Req 15.4)."""

    def test_all_12_terraform_modules_still_available(self):
        """All 12 Golden Modules must remain accessible after interface refactor."""
        inv = GoldenModulesInventory()
        modules = inv.list_available_modules()
        assert len(modules) == 12

    def test_terraform_generator_still_produces_hcl(self):
        """ConfigurationGenerator must still produce valid HCL content."""
        gen = ConfigurationGenerator()
        schema = INVENTORY.get_module_schema(ResourceType.S3_BUCKET)
        request = make_request(
            resource_type=ResourceType.S3_BUCKET,
            parameters={"bucket_name": "compat-test"},
        )
        result = gen.generate_tfvars(request, schema)
        assert isinstance(result, TfvarsContent)
        assert "=" in result.content  # HCL assignment syntax

    def test_terraform_request_technology_type_unchanged(self):
        """Existing Terraform requests must not require technology_type to be set."""
        # Simulate legacy code that doesn't set technology_type
        request = StructuredRequest(
            resource_type=ResourceType.LAMBDA_FUNCTION,
            parameters={"function_name": "my-fn", "runtime": "python3.11"},
            environment=Environment.PRODUCTION,
            confidence=0.98,
            user_justification="Legacy request",
            request_id="req-legacy-001",
            timestamp=datetime(2024, 1, 15),
            # technology_type intentionally omitted — should default to TERRAFORM
        )
        assert request.technology_type == TechnologyType.TERRAFORM

    def test_configuration_generator_works_with_all_resource_types(self):
        """ConfigurationGenerator must work for all 12 resource types (Req 15.4)."""
        gen = ConfigurationGenerator()
        inv = GoldenModulesInventory()

        for resource_type in ResourceType:
            schema = inv.get_module_schema(resource_type)
            # Build minimal valid parameters
            params = {p.name: "test-value" for p in schema.required_parameters if p.name != "environment"}
            request = StructuredRequest(
                resource_type=resource_type,
                parameters=params,
                environment=Environment.DEVELOPMENT,
                confidence=0.9,
                user_justification="Compat test",
                request_id=f"req-{resource_type.value}",
                timestamp=datetime(2024, 1, 15),
            )
            result = gen.generate_tfvars(request, schema)
            assert isinstance(result, TfvarsContent), f"Failed for {resource_type}"
            assert result.resource_type == resource_type
