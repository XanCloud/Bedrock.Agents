"""Unit tests for ConfigurationGenerator component."""

from datetime import datetime

import pytest

from src.bedrock_iac_agent import (
    ConfigurationGenerator,
    Environment,
    GoldenModulesInventory,
    NamingConventions,
    ResourceType,
    StructuredRequest,
    TfvarsContent,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

INVENTORY = GoldenModulesInventory()


def make_request(
    resource_type: ResourceType = ResourceType.S3_BUCKET,
    parameters: dict | None = None,
    environment: Environment = Environment.DEVELOPMENT,
    justification: str = "Test justification",
) -> StructuredRequest:
    return StructuredRequest(
        resource_type=resource_type,
        parameters=parameters or {},
        environment=environment,
        confidence=0.95,
        user_justification=justification,
        request_id="req-test-001",
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
    )


@pytest.fixture
def generator() -> ConfigurationGenerator:
    return ConfigurationGenerator()


@pytest.fixture
def s3_schema():
    return INVENTORY.get_module_schema(ResourceType.S3_BUCKET)


@pytest.fixture
def ec2_schema():
    return INVENTORY.get_module_schema(ResourceType.EC2_INSTANCE)


@pytest.fixture
def rds_schema():
    return INVENTORY.get_module_schema(ResourceType.RDS_DATABASE)


@pytest.fixture
def lambda_schema():
    return INVENTORY.get_module_schema(ResourceType.LAMBDA_FUNCTION)


# ---------------------------------------------------------------------------
# generate_tfvars — basic contract
# ---------------------------------------------------------------------------


class TestGenerateTfvarsBasicContract:
    """Test that generate_tfvars returns a well-formed TfvarsContent."""

    def test_returns_tfvars_content_instance(self, generator, s3_schema):
        request = make_request(
            parameters={"bucket_name": "my-data"},
        )
        result = generator.generate_tfvars(request, s3_schema)
        assert isinstance(result, TfvarsContent)

    def test_content_is_non_empty_string(self, generator, s3_schema):
        request = make_request(parameters={"bucket_name": "my-data"})
        result = generator.generate_tfvars(request, s3_schema)
        assert isinstance(result.content, str)
        assert len(result.content) > 0

    def test_environment_matches_request(self, generator, s3_schema):
        request = make_request(
            parameters={"bucket_name": "my-data"},
            environment=Environment.PRODUCTION,
        )
        result = generator.generate_tfvars(request, s3_schema)
        assert result.environment == Environment.PRODUCTION

    def test_resource_type_matches_request(self, generator, s3_schema):
        request = make_request(parameters={"bucket_name": "my-data"})
        result = generator.generate_tfvars(request, s3_schema)
        assert result.resource_type == ResourceType.S3_BUCKET

    def test_generated_at_is_datetime(self, generator, s3_schema):
        request = make_request(parameters={"bucket_name": "my-data"})
        result = generator.generate_tfvars(request, s3_schema)
        assert isinstance(result.generated_at, datetime)

    def test_file_path_contains_environment(self, generator, s3_schema):
        request = make_request(
            parameters={"bucket_name": "my-data"},
            environment=Environment.STAGING,
        )
        result = generator.generate_tfvars(request, s3_schema)
        assert "staging" in result.file_path

    def test_file_path_contains_resource_type(self, generator, s3_schema):
        request = make_request(parameters={"bucket_name": "my-data"})
        result = generator.generate_tfvars(request, s3_schema)
        assert "s3_bucket" in result.file_path

    def test_raises_on_resource_type_mismatch(self, generator, ec2_schema):
        """generate_tfvars must raise ValueError when request and schema types differ."""
        request = make_request(
            resource_type=ResourceType.S3_BUCKET,
            parameters={"bucket_name": "my-data"},
        )
        with pytest.raises(ValueError, match="mismatch"):
            generator.generate_tfvars(request, ec2_schema)


# ---------------------------------------------------------------------------
# generate_tfvars — HCL content
# ---------------------------------------------------------------------------


class TestGenerateTfvarsHclContent:
    """Test that the generated HCL content is correctly formatted."""

    def test_environment_parameter_present_in_content(self, generator, s3_schema):
        request = make_request(
            parameters={"bucket_name": "my-data"},
            environment=Environment.DEVELOPMENT,
        )
        result = generator.generate_tfvars(request, s3_schema)
        assert 'environment = "dev"' in result.content

    def test_string_values_are_quoted(self, generator, s3_schema):
        request = make_request(parameters={"bucket_name": "my-data"})
        result = generator.generate_tfvars(request, s3_schema)
        # bucket_name should appear as a quoted string
        assert '"' in result.content

    def test_boolean_values_are_lowercase(self, generator, s3_schema):
        """Security params like encryption_enabled should be lowercase true/false."""
        request = make_request(parameters={"bucket_name": "my-data"})
        result = generator.generate_tfvars(request, s3_schema)
        # Should not contain Python-style True/False
        assert "True" not in result.content
        assert "False" not in result.content

    def test_content_uses_equals_assignment(self, generator, s3_schema):
        request = make_request(parameters={"bucket_name": "my-data"})
        result = generator.generate_tfvars(request, s3_schema)
        assert " = " in result.content

    def test_content_ends_with_newline(self, generator, s3_schema):
        request = make_request(parameters={"bucket_name": "my-data"})
        result = generator.generate_tfvars(request, s3_schema)
        assert result.content.endswith("\n")


# ---------------------------------------------------------------------------
# generate_tfvars — security parameter preservation
# ---------------------------------------------------------------------------


class TestSecurityParameterPreservation:
    """Test that security parameters cannot be overridden by user input."""

    def test_security_param_not_overridden_by_user(self, generator, s3_schema):
        """User tries to set encryption_enabled=false; module default (true) must win."""
        request = make_request(
            parameters={
                "bucket_name": "my-data",
                "encryption_enabled": False,  # attempt to override
            }
        )
        result = generator.generate_tfvars(request, s3_schema)
        # The Golden Module default is "true"; user's False must be ignored
        assert "encryption_enabled = false" not in result.content

    def test_security_param_present_in_output(self, generator, s3_schema):
        """Security parameters should always appear in the output."""
        request = make_request(parameters={"bucket_name": "my-data"})
        result = generator.generate_tfvars(request, s3_schema)
        assert "encryption_enabled" in result.content
        assert "versioning_enabled" in result.content

    def test_security_param_override_generates_warning(self, generator, s3_schema, caplog):
        """Attempting to override a security parameter should log a warning."""
        import logging

        request = make_request(
            parameters={
                "bucket_name": "my-data",
                "encryption_enabled": False,
            }
        )
        with caplog.at_level(logging.WARNING, logger="src.bedrock_iac_agent.configuration_generator"):
            generator.generate_tfvars(request, s3_schema)
        assert any("encryption_enabled" in msg for msg in caplog.messages)

    def test_rds_security_params_preserved(self, generator, rds_schema):
        """RDS storage_encrypted and backup_retention_period must be preserved."""
        request = make_request(
            resource_type=ResourceType.RDS_DATABASE,
            parameters={
                "db_name": "mydb",
                "engine": "postgres",
                "storage_encrypted": False,  # attempt to override
                "backup_retention_period": 0,  # attempt to override
            },
        )
        result = generator.generate_tfvars(request, rds_schema)
        # Module defaults are "true" and "7"
        assert "storage_encrypted = false" not in result.content
        assert "backup_retention_period = 0" not in result.content


# ---------------------------------------------------------------------------
# apply_naming_conventions
# ---------------------------------------------------------------------------


class TestApplyNamingConventions:
    """Test naming convention application."""

    def test_prefix_is_prepended(self, generator):
        conventions = NamingConventions(
            prefix="mycompany",
            environment_suffix=False,
            separator="-",
            max_length=63,
            allowed_characters=r"[a-z0-9\-]",
        )
        result = generator.apply_naming_conventions("data", Environment.DEVELOPMENT, conventions)
        assert result.startswith("mycompany-")

    def test_environment_suffix_appended_when_enabled(self, generator):
        conventions = NamingConventions(
            prefix="",
            environment_suffix=True,
            separator="-",
            max_length=63,
            allowed_characters=r"[a-z0-9\-]",
        )
        result = generator.apply_naming_conventions("data", Environment.DEVELOPMENT, conventions)
        assert result.endswith("-dev")

    def test_environment_suffix_not_appended_when_disabled(self, generator):
        conventions = NamingConventions(
            prefix="",
            environment_suffix=False,
            separator="-",
            max_length=63,
            allowed_characters=r"[a-z0-9\-]",
        )
        result = generator.apply_naming_conventions("data", Environment.DEVELOPMENT, conventions)
        assert not result.endswith("-dev")

    def test_name_is_lowercased(self, generator):
        conventions = NamingConventions(
            prefix="",
            environment_suffix=False,
            separator="-",
            max_length=63,
            allowed_characters=r"[a-z0-9\-]",
        )
        result = generator.apply_naming_conventions("MyBucket", Environment.DEVELOPMENT, conventions)
        assert result == result.lower()

    def test_spaces_replaced_with_separator(self, generator):
        conventions = NamingConventions(
            prefix="",
            environment_suffix=False,
            separator="-",
            max_length=63,
            allowed_characters=r"[a-z0-9\-]",
        )
        result = generator.apply_naming_conventions("my bucket", Environment.DEVELOPMENT, conventions)
        assert " " not in result
        assert "-" in result

    def test_max_length_enforced(self, generator):
        conventions = NamingConventions(
            prefix="",
            environment_suffix=False,
            separator="-",
            max_length=10,
            allowed_characters=r"[a-z0-9\-]",
        )
        result = generator.apply_naming_conventions(
            "a-very-long-resource-name", Environment.DEVELOPMENT, conventions
        )
        assert len(result) <= 10

    def test_full_naming_convention(self, generator):
        conventions = NamingConventions(
            prefix="mycompany",
            environment_suffix=True,
            separator="-",
            max_length=63,
            allowed_characters=r"[a-z0-9\-]",
        )
        result = generator.apply_naming_conventions("data", Environment.DEVELOPMENT, conventions)
        assert result == "mycompany-data-dev"

    def test_naming_applied_to_bucket_name_in_tfvars(self, generator, s3_schema):
        """Naming conventions should be applied to bucket_name in generated tfvars."""
        conventions = NamingConventions(
            prefix="corp",
            environment_suffix=True,
            separator="-",
            max_length=63,
            allowed_characters=r"[a-z0-9\-]",
        )
        request = make_request(parameters={"bucket_name": "logs"})
        result = generator.generate_tfvars(request, s3_schema, naming_conventions=conventions)
        assert "corp-logs-dev" in result.content


# ---------------------------------------------------------------------------
# validate_parameters
# ---------------------------------------------------------------------------


class TestValidateParameters:
    """Test parameter validation against Golden Module schema."""

    def test_valid_parameters_return_is_valid_true(self, generator, s3_schema):
        params = {"bucket_name": "my-data", "environment": "dev"}
        result = generator.validate_parameters(params, s3_schema)
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True

    def test_missing_required_parameter_returns_error(self, generator, s3_schema):
        params = {}  # bucket_name is required
        result = generator.validate_parameters(params, s3_schema)
        assert result.is_valid is False
        assert any("bucket_name" in e for e in result.errors)

    def test_security_parameter_override_returns_warning(self, generator, s3_schema):
        params = {"bucket_name": "my-data", "encryption_enabled": False}
        result = generator.validate_parameters(params, s3_schema)
        assert any("encryption_enabled" in w for w in result.warnings)

    def test_unknown_parameter_returns_warning(self, generator, s3_schema):
        params = {"bucket_name": "my-data", "unknown_param": "value"}
        result = generator.validate_parameters(params, s3_schema)
        assert any("unknown_param" in w for w in result.warnings)

    def test_wrong_type_returns_error(self, generator, ec2_schema):
        """instance_type expects string; passing a number should produce an error."""
        params = {
            "instance_name": "web",
            "instance_type": 123,  # should be string
            "environment": "dev",
        }
        result = generator.validate_parameters(params, ec2_schema)
        assert result.is_valid is False
        assert any("instance_type" in e for e in result.errors)

    def test_valid_ec2_parameters(self, generator, ec2_schema):
        params = {
            "instance_name": "web-server",
            "instance_type": "t3.micro",
            "environment": "dev",
        }
        result = generator.validate_parameters(params, ec2_schema)
        assert result.is_valid is True
        assert result.errors == []

    def test_validation_result_has_lists(self, generator, s3_schema):
        params = {"bucket_name": "my-data"}
        result = generator.validate_parameters(params, s3_schema)
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)


# ---------------------------------------------------------------------------
# add_comments
# ---------------------------------------------------------------------------


class TestAddComments:
    """Test that add_comments produces a properly commented tfvars."""

    def test_returns_string(self, generator):
        result = generator.add_comments("key = \"value\"\n")
        assert isinstance(result, str)

    def test_original_content_preserved(self, generator):
        original = 'key = "value"\n'
        result = generator.add_comments(original)
        assert original in result

    def test_header_comment_present(self, generator):
        result = generator.add_comments("key = \"value\"\n")
        assert result.startswith("#")

    def test_request_id_in_comments(self, generator, s3_schema):
        request = make_request(parameters={"bucket_name": "my-data"})
        result = generator.generate_tfvars(request, s3_schema)
        assert "req-test-001" in result.content

    def test_resource_type_in_comments(self, generator, s3_schema):
        request = make_request(parameters={"bucket_name": "my-data"})
        result = generator.generate_tfvars(request, s3_schema)
        assert "s3_bucket" in result.content

    def test_environment_in_comments(self, generator, s3_schema):
        request = make_request(
            parameters={"bucket_name": "my-data"},
            environment=Environment.PRODUCTION,
        )
        result = generator.generate_tfvars(request, s3_schema)
        assert "prod" in result.content

    def test_module_path_in_comments(self, generator, s3_schema):
        request = make_request(parameters={"bucket_name": "my-data"})
        result = generator.generate_tfvars(request, s3_schema)
        assert "modules/s3_bucket" in result.content

    def test_warnings_included_in_comments(self, generator, s3_schema):
        request = make_request(
            parameters={
                "bucket_name": "my-data",
                "encryption_enabled": False,  # triggers warning
            }
        )
        result = generator.generate_tfvars(request, s3_schema)
        assert "encryption_enabled" in result.content


# ---------------------------------------------------------------------------
# generate_tfvars — all 12 Golden Modules
# ---------------------------------------------------------------------------


class TestGenerateTfvarsAllModules:
    """Test tfvars generation for all 12 Golden Modules."""

    @pytest.mark.parametrize(
        "resource_type, extra_params",
        [
            (ResourceType.S3_BUCKET, {"bucket_name": "my-bucket"}),
            (ResourceType.EC2_INSTANCE, {"instance_name": "web", "instance_type": "t3.micro"}),
            (ResourceType.RDS_DATABASE, {"db_name": "mydb", "engine": "postgres"}),
            (ResourceType.LAMBDA_FUNCTION, {"function_name": "my-fn", "runtime": "python3.11"}),
            (ResourceType.API_GATEWAY, {"api_name": "my-api"}),
            (ResourceType.DYNAMODB_TABLE, {"table_name": "my-table", "hash_key": "id"}),
            (ResourceType.VPC, {"vpc_name": "my-vpc", "cidr_block": "10.0.0.0/16"}),
            (ResourceType.SECURITY_GROUP, {"security_group_name": "my-sg", "vpc_id": "vpc-12345678"}),
            (ResourceType.IAM_ROLE, {"role_name": "my-role", "trusted_services": ["lambda.amazonaws.com"]}),
            (ResourceType.CLOUDWATCH_LOG_GROUP, {"log_group_name": "my-logs"}),
            (ResourceType.SNS_TOPIC, {"topic_name": "my-topic"}),
            (ResourceType.SQS_QUEUE, {"queue_name": "my-queue"}),
        ],
    )
    def test_generate_tfvars_for_module(self, generator, resource_type, extra_params):
        schema = INVENTORY.get_module_schema(resource_type)
        request = make_request(resource_type=resource_type, parameters=extra_params)
        result = generator.generate_tfvars(request, schema)

        assert isinstance(result, TfvarsContent)
        assert len(result.content) > 0
        assert result.resource_type == resource_type
        assert result.environment == Environment.DEVELOPMENT
        # HCL assignment syntax must be present
        assert " = " in result.content
        # Environment must be set
        assert "environment" in result.content


# ---------------------------------------------------------------------------
# File path convention
# ---------------------------------------------------------------------------


class TestFilePath:
    """Test the generated file path follows the expected convention."""

    def test_file_path_format(self, generator, s3_schema):
        request = make_request(
            parameters={"bucket_name": "my-data"},
            environment=Environment.STAGING,
        )
        result = generator.generate_tfvars(request, s3_schema)
        assert result.file_path == "environments/staging/s3_bucket/terraform.tfvars"

    def test_file_path_dev_environment(self, generator, s3_schema):
        request = make_request(
            parameters={"bucket_name": "my-data"},
            environment=Environment.DEVELOPMENT,
        )
        result = generator.generate_tfvars(request, s3_schema)
        assert result.file_path == "environments/dev/s3_bucket/terraform.tfvars"

    def test_file_path_prod_environment(self, generator, s3_schema):
        request = make_request(
            parameters={"bucket_name": "my-data"},
            environment=Environment.PRODUCTION,
        )
        result = generator.generate_tfvars(request, s3_schema)
        assert result.file_path == "environments/prod/s3_bucket/terraform.tfvars"


# ---------------------------------------------------------------------------
# HCL value formatting
# ---------------------------------------------------------------------------


class TestHclValueFormatting:
    """Test the internal HCL value formatter."""

    def test_string_value_quoted(self, generator):
        result = generator._to_hcl_value("hello")
        assert result == '"hello"'

    def test_bool_true_lowercase(self, generator):
        assert generator._to_hcl_value(True) == "true"

    def test_bool_false_lowercase(self, generator):
        assert generator._to_hcl_value(False) == "false"

    def test_integer_unquoted(self, generator):
        assert generator._to_hcl_value(42) == "42"

    def test_float_unquoted(self, generator):
        assert generator._to_hcl_value(3.14) == "3.14"

    def test_list_formatted(self, generator):
        result = generator._to_hcl_value(["a", "b"])
        assert result == '["a", "b"]'

    def test_empty_list(self, generator):
        assert generator._to_hcl_value([]) == "[]"

    def test_dict_formatted(self, generator):
        result = generator._to_hcl_value({"key": "val"})
        assert "key" in result
        assert "val" in result

    def test_empty_dict(self, generator):
        assert generator._to_hcl_value({}) == "{}"

    def test_string_true_becomes_lowercase(self, generator):
        assert generator._to_hcl_value("true") == "true"

    def test_string_false_becomes_lowercase(self, generator):
        assert generator._to_hcl_value("false") == "false"

    def test_numeric_string_unquoted(self, generator):
        assert generator._to_hcl_value("7") == "7"


# ---------------------------------------------------------------------------
# ConfigurationGenerator is importable from package
# ---------------------------------------------------------------------------


class TestPackageExport:
    """Verify ConfigurationGenerator is exported from the package."""

    def test_importable_from_package(self):
        from src.bedrock_iac_agent import ConfigurationGenerator as CG

        assert CG is not None

    def test_is_instantiable(self):
        gen = ConfigurationGenerator()
        assert gen is not None
