"""Unit tests for data models."""

import json
from datetime import datetime
from typing import Any, Dict

import pytest

from bedrock_iac_agent.models import (
    AgentResponse,
    ConversationContext,
    Environment,
    ErrorResponse,
    FileChange,
    GitHubCredentials,
    ModuleInfo,
    ModuleSchema,
    NamingConventions,
    Parameter,
    PullRequest,
    PullRequestDetails,
    ResourceType,
    StructuredRequest,
    TechnologyType,
    TfvarsContent,
    ValidationResult,
)


class TestResourceTypeEnum:
    """Tests for ResourceType enum."""

    def test_all_resource_types_exist(self):
        """Test that all 12 resource types are defined."""
        expected_types = [
            "s3_bucket",
            "ec2_instance",
            "rds_database",
            "lambda_function",
            "api_gateway",
            "dynamodb_table",
            "vpc",
            "security_group",
            "iam_role",
            "cloudwatch_log_group",
            "sns_topic",
            "sqs_queue",
        ]
        actual_values = [rt.value for rt in ResourceType]
        assert len(actual_values) == 12
        for expected in expected_types:
            assert expected in actual_values

    def test_resource_type_by_value(self):
        """Test accessing ResourceType by value."""
        assert ResourceType("s3_bucket") == ResourceType.S3_BUCKET
        assert ResourceType("ec2_instance") == ResourceType.EC2_INSTANCE
        assert ResourceType("rds_database") == ResourceType.RDS_DATABASE

    def test_resource_type_by_name(self):
        """Test accessing ResourceType by name."""
        assert ResourceType.S3_BUCKET.value == "s3_bucket"
        assert ResourceType.LAMBDA_FUNCTION.value == "lambda_function"
        assert ResourceType.VPC.value == "vpc"

    def test_invalid_resource_type_raises_error(self):
        """Test that invalid resource type raises ValueError."""
        with pytest.raises(ValueError):
            ResourceType("invalid_resource")


class TestEnvironmentEnum:
    """Tests for Environment enum."""

    def test_all_environments_exist(self):
        """Test that all environments are defined."""
        expected_envs = ["dev", "staging", "prod"]
        actual_values = [env.value for env in Environment]
        assert len(actual_values) == 3
        for expected in expected_envs:
            assert expected in actual_values

    def test_environment_by_value(self):
        """Test accessing Environment by value."""
        assert Environment("dev") == Environment.DEVELOPMENT
        assert Environment("staging") == Environment.STAGING
        assert Environment("prod") == Environment.PRODUCTION

    def test_environment_by_name(self):
        """Test accessing Environment by name."""
        assert Environment.DEVELOPMENT.value == "dev"
        assert Environment.STAGING.value == "staging"
        assert Environment.PRODUCTION.value == "prod"

    def test_invalid_environment_raises_error(self):
        """Test that invalid environment raises ValueError."""
        with pytest.raises(ValueError):
            Environment("invalid_env")


class TestTechnologyTypeEnum:
    """Tests for TechnologyType enum – Requirement 15.3."""

    def test_terraform_value(self):
        """TechnologyType.TERRAFORM should have value 'terraform'."""
        assert TechnologyType.TERRAFORM.value == "terraform"

    def test_kubernetes_value(self):
        """TechnologyType.KUBERNETES should have value 'kubernetes'."""
        assert TechnologyType.KUBERNETES.value == "kubernetes"

    def test_technology_type_by_value(self):
        """TechnologyType should be accessible by value string."""
        assert TechnologyType("terraform") == TechnologyType.TERRAFORM
        assert TechnologyType("kubernetes") == TechnologyType.KUBERNETES

    def test_invalid_technology_type_raises_error(self):
        """Invalid technology type string should raise ValueError."""
        with pytest.raises(ValueError):
            TechnologyType("ansible")


class TestStructuredRequest:
    """Tests for StructuredRequest dataclass."""

    def test_instantiation_with_all_fields(self):
        """Test creating StructuredRequest with all required fields."""
        timestamp = datetime.now()
        request = StructuredRequest(
            resource_type=ResourceType.S3_BUCKET,
            parameters={"bucket_name": "test-bucket"},
            environment=Environment.DEVELOPMENT,
            confidence=0.95,
            user_justification="Need storage for logs",
            request_id="req-123",
            timestamp=timestamp,
        )

        assert request.resource_type == ResourceType.S3_BUCKET
        assert request.parameters == {"bucket_name": "test-bucket"}
        assert request.environment == Environment.DEVELOPMENT
        assert request.confidence == 0.95
        assert request.user_justification == "Need storage for logs"
        assert request.request_id == "req-123"
        assert request.timestamp == timestamp

    def test_confidence_range_validation(self):
        """Test that confidence values are within expected range."""
        timestamp = datetime.now()
        # Valid confidence values
        for confidence in [0.0, 0.5, 1.0]:
            request = StructuredRequest(
                resource_type=ResourceType.S3_BUCKET,
                parameters={},
                environment=Environment.DEVELOPMENT,
                confidence=confidence,
                user_justification="test",
                request_id="req-123",
                timestamp=timestamp,
            )
            assert request.confidence == confidence

    def test_parameters_can_be_empty_dict(self):
        """Test that parameters can be an empty dictionary."""
        request = StructuredRequest(
            resource_type=ResourceType.VPC,
            parameters={},
            environment=Environment.PRODUCTION,
            confidence=0.8,
            user_justification="test",
            request_id="req-456",
            timestamp=datetime.now(),
        )
        assert request.parameters == {}

    def test_parameters_can_contain_nested_structures(self):
        """Test that parameters can contain complex nested data."""
        complex_params = {
            "name": "my-lambda",
            "runtime": "python3.9",
            "environment_vars": {"KEY1": "value1", "KEY2": "value2"},
            "tags": ["production", "critical"],
        }
        request = StructuredRequest(
            resource_type=ResourceType.LAMBDA_FUNCTION,
            parameters=complex_params,
            environment=Environment.PRODUCTION,
            confidence=0.9,
            user_justification="test",
            request_id="req-789",
            timestamp=datetime.now(),
        )
        assert request.parameters == complex_params

    def test_technology_type_defaults_to_terraform(self):
        """StructuredRequest should default technology_type to TERRAFORM for backward compatibility."""
        request = StructuredRequest(
            resource_type=ResourceType.S3_BUCKET,
            parameters={},
            environment=Environment.DEVELOPMENT,
            confidence=0.9,
            user_justification="test",
            request_id="req-001",
            timestamp=datetime.now(),
        )
        assert request.technology_type == TechnologyType.TERRAFORM

    def test_technology_type_can_be_set_to_kubernetes(self):
        """StructuredRequest should accept KUBERNETES as technology_type."""
        request = StructuredRequest(
            resource_type=ResourceType.S3_BUCKET,
            parameters={},
            environment=Environment.DEVELOPMENT,
            confidence=0.9,
            user_justification="test",
            request_id="req-002",
            timestamp=datetime.now(),
            technology_type=TechnologyType.KUBERNETES,
        )
        assert request.technology_type == TechnologyType.KUBERNETES

    def test_technology_type_is_technology_agnostic(self):
        """StructuredRequest should support all TechnologyType values."""
        for tech in TechnologyType:
            request = StructuredRequest(
                resource_type=ResourceType.EC2_INSTANCE,
                parameters={},
                environment=Environment.STAGING,
                confidence=0.85,
                user_justification="test",
                request_id=f"req-{tech.value}",
                timestamp=datetime.now(),
                technology_type=tech,
            )
            assert request.technology_type == tech


class TestParameter:
    """Tests for Parameter dataclass."""

    def test_instantiation_required_fields_only(self):
        """Test creating Parameter with only required fields."""
        param = Parameter(
            name="bucket_name",
            type="string",
            required=True,
            default=None,
            description="Name of the S3 bucket",
        )

        assert param.name == "bucket_name"
        assert param.type == "string"
        assert param.required is True
        assert param.default is None
        assert param.description == "Name of the S3 bucket"
        assert param.validation_rules is None
        assert param.is_security_parameter is False

    def test_instantiation_with_all_fields(self):
        """Test creating Parameter with all fields."""
        validation_rules = {"min_length": 3, "max_length": 63}
        param = Parameter(
            name="encryption_key",
            type="string",
            required=True,
            default="AES256",
            description="Encryption algorithm",
            validation_rules=validation_rules,
            is_security_parameter=True,
        )

        assert param.name == "encryption_key"
        assert param.is_security_parameter is True
        assert param.validation_rules == validation_rules

    def test_optional_parameter_with_default(self):
        """Test creating optional parameter with default value."""
        param = Parameter(
            name="versioning_enabled",
            type="bool",
            required=False,
            default=True,
            description="Enable versioning",
        )

        assert param.required is False
        assert param.default is True


class TestModuleSchema:
    """Tests for ModuleSchema dataclass."""

    def test_instantiation_with_all_fields(self):
        """Test creating ModuleSchema with all fields."""
        required_params = [
            Parameter(
                name="bucket_name",
                type="string",
                required=True,
                default=None,
                description="Bucket name",
            )
        ]
        optional_params = [
            Parameter(
                name="versioning",
                type="bool",
                required=False,
                default=False,
                description="Enable versioning",
            )
        ]
        security_params = [
            Parameter(
                name="encryption",
                type="bool",
                required=True,
                default=True,
                description="Enable encryption",
                is_security_parameter=True,
            )
        ]

        schema = ModuleSchema(
            resource_type=ResourceType.S3_BUCKET,
            module_path="modules/s3",
            required_parameters=required_params,
            optional_parameters=optional_params,
            security_parameters=security_params,
            naming_pattern="{project}-{env}-{resource}-{suffix}",
            description="S3 bucket module",
            version="1.0.0",
        )

        assert schema.resource_type == ResourceType.S3_BUCKET
        assert schema.module_path == "modules/s3"
        assert len(schema.required_parameters) == 1
        assert len(schema.optional_parameters) == 1
        assert len(schema.security_parameters) == 1
        assert schema.naming_pattern == "{project}-{env}-{resource}-{suffix}"
        assert schema.version == "1.0.0"

    def test_empty_parameter_lists(self):
        """Test ModuleSchema with empty parameter lists."""
        schema = ModuleSchema(
            resource_type=ResourceType.VPC,
            module_path="modules/vpc",
            required_parameters=[],
            optional_parameters=[],
            security_parameters=[],
            naming_pattern="{project}-{env}-vpc",
            description="VPC module",
            version="1.0.0",
        )

        assert len(schema.required_parameters) == 0
        assert len(schema.optional_parameters) == 0
        assert len(schema.security_parameters) == 0


class TestTfvarsContent:
    """Tests for TfvarsContent dataclass."""

    def test_instantiation_with_all_fields(self):
        """Test creating TfvarsContent with all fields."""
        timestamp = datetime.now()
        tfvars = TfvarsContent(
            content='bucket_name = "my-bucket"\nencryption = true',
            file_path="environments/dev/terraform.tfvars",
            environment=Environment.DEVELOPMENT,
            resource_type=ResourceType.S3_BUCKET,
            generated_at=timestamp,
        )

        assert "bucket_name" in tfvars.content
        assert tfvars.file_path == "environments/dev/terraform.tfvars"
        assert tfvars.environment == Environment.DEVELOPMENT
        assert tfvars.resource_type == ResourceType.S3_BUCKET
        assert tfvars.generated_at == timestamp

    def test_content_can_be_multiline(self):
        """Test that content can contain multiline HCL."""
        content = """
bucket_name = "my-bucket"
environment = "dev"
tags = {
  Project = "MyProject"
  Environment = "Development"
}
"""
        tfvars = TfvarsContent(
            content=content,
            file_path="terraform.tfvars",
            environment=Environment.DEVELOPMENT,
            resource_type=ResourceType.S3_BUCKET,
            generated_at=datetime.now(),
        )

        assert "tags = {" in tfvars.content
        assert tfvars.content.count("\n") > 1


class TestPullRequestDetails:
    """Tests for PullRequestDetails dataclass."""

    def test_instantiation_with_all_fields(self):
        """Test creating PullRequestDetails with all fields."""
        metadata = {"request_id": "req-123", "conversation_id": "conv-456"}
        pr_details = PullRequestDetails(
            title="Add S3 bucket for development",
            description="Creates S3 bucket with encryption enabled",
            source_branch="iac-agent/s3-bucket/dev/20240115",
            target_branch="main",
            labels=["infrastructure", "automated"],
            reviewers=["team-lead", "security-team"],
            metadata=metadata,
        )

        assert pr_details.title == "Add S3 bucket for development"
        assert pr_details.source_branch == "iac-agent/s3-bucket/dev/20240115"
        assert pr_details.target_branch == "main"
        assert len(pr_details.labels) == 2
        assert len(pr_details.reviewers) == 2
        assert pr_details.metadata["request_id"] == "req-123"

    def test_empty_lists_allowed(self):
        """Test that labels and reviewers can be empty lists."""
        pr_details = PullRequestDetails(
            title="Test PR",
            description="Test description",
            source_branch="test-branch",
            target_branch="main",
            labels=[],
            reviewers=[],
            metadata={},
        )

        assert pr_details.labels == []
        assert pr_details.reviewers == []
        assert pr_details.metadata == {}


class TestPullRequest:
    """Tests for PullRequest dataclass."""

    def test_instantiation_with_all_fields(self):
        """Test creating PullRequest with all fields."""
        timestamp = datetime.now()
        pr = PullRequest(
            url="https://github.com/org/repo/pull/123",
            number=123,
            branch_name="iac-agent/s3-bucket/dev/20240115",
            created_at=timestamp,
        )

        assert pr.url == "https://github.com/org/repo/pull/123"
        assert pr.number == 123
        assert pr.branch_name == "iac-agent/s3-bucket/dev/20240115"
        assert pr.created_at == timestamp


class TestConversationContext:
    """Tests for ConversationContext dataclass."""

    def test_instantiation_with_required_fields_only(self):
        """Test creating ConversationContext with only required fields."""
        context = ConversationContext(
            session_id="session-123",
            user_id="user@example.com",
        )

        assert context.session_id == "session-123"
        assert context.user_id == "user@example.com"
        assert context.history == []
        assert context.current_request is None
        assert context.pending_clarifications == []
        assert context.preferences == {}

    def test_instantiation_with_all_fields(self):
        """Test creating ConversationContext with all fields."""
        history = [
            {"role": "user", "content": "I need an S3 bucket"},
            {"role": "assistant", "content": "What environment?"},
        ]
        request = StructuredRequest(
            resource_type=ResourceType.S3_BUCKET,
            parameters={},
            environment=Environment.DEVELOPMENT,
            confidence=0.8,
            user_justification="test",
            request_id="req-123",
            timestamp=datetime.now(),
        )
        context = ConversationContext(
            session_id="session-123",
            user_id="user@example.com",
            history=history,
            current_request=request,
            pending_clarifications=["What is the bucket name?"],
            preferences={"default_env": "dev"},
        )

        assert len(context.history) == 2
        assert context.current_request is not None
        assert len(context.pending_clarifications) == 1
        assert context.preferences["default_env"] == "dev"

    def test_history_can_be_appended(self):
        """Test that history list can be modified."""
        context = ConversationContext(
            session_id="session-123",
            user_id="user@example.com",
        )

        context.history.append({"role": "user", "content": "Hello"})
        assert len(context.history) == 1
        assert context.history[0]["content"] == "Hello"


class TestAgentResponse:
    """Tests for AgentResponse dataclass."""

    def test_instantiation_with_required_fields_only(self):
        """Test creating AgentResponse with only required fields."""
        response = AgentResponse(message="PR created successfully")

        assert response.message == "PR created successfully"
        assert response.pr_url is None
        assert response.status == "success"
        assert response.next_steps == []
        assert response.metadata == {}

    def test_instantiation_with_all_fields(self):
        """Test creating AgentResponse with all fields."""
        response = AgentResponse(
            message="PR created successfully",
            pr_url="https://github.com/org/repo/pull/123",
            status="success",
            next_steps=["Review the PR", "Approve and merge"],
            metadata={"request_id": "req-123", "duration_ms": 1500},
        )

        assert response.pr_url == "https://github.com/org/repo/pull/123"
        assert response.status == "success"
        assert len(response.next_steps) == 2
        assert response.metadata["duration_ms"] == 1500

    def test_different_status_values(self):
        """Test AgentResponse with different status values."""
        for status in ["success", "error", "needs_clarification"]:
            response = AgentResponse(message="Test", status=status)
            assert response.status == status


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_instantiation_valid_result(self):
        """Test creating ValidationResult for valid case."""
        result = ValidationResult(is_valid=True)

        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_instantiation_invalid_result_with_errors(self):
        """Test creating ValidationResult with errors."""
        result = ValidationResult(
            is_valid=False,
            errors=["Missing required parameter: bucket_name", "Invalid environment"],
            warnings=["Consider enabling versioning"],
        )

        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1

    def test_errors_and_warnings_can_be_modified(self):
        """Test that errors and warnings lists can be modified."""
        result = ValidationResult(is_valid=True)

        result.warnings.append("This is a warning")
        assert len(result.warnings) == 1


class TestGitHubCredentials:
    """Tests for GitHubCredentials dataclass."""

    def test_instantiation_with_all_fields(self):
        """Test creating GitHubCredentials with all fields."""
        creds = GitHubCredentials(
            token="ghp_1234567890abcdef",
            organization="my-org",
            repository="my-repo",
        )

        assert creds.token == "ghp_1234567890abcdef"
        assert creds.organization == "my-org"
        assert creds.repository == "my-repo"


class TestNamingConventions:
    """Tests for NamingConventions dataclass."""

    def test_instantiation_with_all_fields(self):
        """Test creating NamingConventions with all fields."""
        conventions = NamingConventions(
            prefix="mycompany",
            environment_suffix=True,
            separator="-",
            max_length=63,
            allowed_characters=r"[a-z0-9-]",
        )

        assert conventions.prefix == "mycompany"
        assert conventions.environment_suffix is True
        assert conventions.separator == "-"
        assert conventions.max_length == 63
        assert conventions.allowed_characters == r"[a-z0-9-]"


class TestErrorResponse:
    """Tests for ErrorResponse dataclass."""

    def test_instantiation_with_all_fields(self):
        """Test creating ErrorResponse with all fields."""
        error = ErrorResponse(
            error_code="AUTH_FAILED",
            error_message="Authentication failed",
            technical_details="Invalid GitHub token",
            suggested_actions=["Verify token", "Generate new token"],
            retry_possible=True,
        )

        assert error.error_code == "AUTH_FAILED"
        assert error.error_message == "Authentication failed"
        assert error.technical_details == "Invalid GitHub token"
        assert len(error.suggested_actions) == 2
        assert error.retry_possible is True

    def test_non_retryable_error(self):
        """Test creating non-retryable error."""
        error = ErrorResponse(
            error_code="INVALID_PARAMS",
            error_message="Invalid parameters",
            technical_details="bucket_name is required",
            suggested_actions=["Provide bucket_name parameter"],
            retry_possible=False,
        )

        assert error.retry_possible is False


class TestModuleInfo:
    """Tests for ModuleInfo dataclass."""

    def test_instantiation_with_all_fields(self):
        """Test creating ModuleInfo with all fields."""
        info = ModuleInfo(
            resource_type=ResourceType.S3_BUCKET,
            name="S3 Bucket",
            description="Secure S3 bucket with encryption",
            version="1.2.0",
        )

        assert info.resource_type == ResourceType.S3_BUCKET
        assert info.name == "S3 Bucket"
        assert info.description == "Secure S3 bucket with encryption"
        assert info.version == "1.2.0"


class TestFileChange:
    """Tests for FileChange dataclass."""

    def test_instantiation_with_all_fields(self):
        """Test creating FileChange with all fields."""
        change = FileChange(
            file_path="environments/dev/terraform.tfvars",
            content='bucket_name = "my-bucket"',
            operation="modify",
        )

        assert change.file_path == "environments/dev/terraform.tfvars"
        assert change.content == 'bucket_name = "my-bucket"'
        assert change.operation == "modify"

    def test_different_operations(self):
        """Test FileChange with different operations."""
        for operation in ["add", "modify", "delete"]:
            change = FileChange(
                file_path="test.txt",
                content="test content",
                operation=operation,
            )
            assert change.operation == operation


class TestDataclassSerialization:
    """Tests for serialization/deserialization of data models."""

    def test_structured_request_to_dict(self):
        """Test converting StructuredRequest to dictionary."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        request = StructuredRequest(
            resource_type=ResourceType.S3_BUCKET,
            parameters={"bucket_name": "test-bucket"},
            environment=Environment.DEVELOPMENT,
            confidence=0.95,
            user_justification="Need storage",
            request_id="req-123",
            timestamp=timestamp,
        )

        # Convert to dict using __dict__
        request_dict = {
            "resource_type": request.resource_type.value,
            "parameters": request.parameters,
            "environment": request.environment.value,
            "confidence": request.confidence,
            "user_justification": request.user_justification,
            "request_id": request.request_id,
            "timestamp": request.timestamp.isoformat(),
        }

        assert request_dict["resource_type"] == "s3_bucket"
        assert request_dict["environment"] == "dev"
        assert request_dict["confidence"] == 0.95

    def test_agent_response_to_dict(self):
        """Test converting AgentResponse to dictionary."""
        response = AgentResponse(
            message="Success",
            pr_url="https://github.com/org/repo/pull/123",
            status="success",
            next_steps=["Review PR"],
            metadata={"request_id": "req-123"},
        )

        response_dict = {
            "message": response.message,
            "pr_url": response.pr_url,
            "status": response.status,
            "next_steps": response.next_steps,
            "metadata": response.metadata,
        }

        assert response_dict["message"] == "Success"
        assert response_dict["pr_url"] == "https://github.com/org/repo/pull/123"
        assert len(response_dict["next_steps"]) == 1

    def test_validation_result_to_dict(self):
        """Test converting ValidationResult to dictionary."""
        result = ValidationResult(
            is_valid=False,
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"],
        )

        result_dict = {
            "is_valid": result.is_valid,
            "errors": result.errors,
            "warnings": result.warnings,
        }

        assert result_dict["is_valid"] is False
        assert len(result_dict["errors"]) == 2
        assert len(result_dict["warnings"]) == 1

    def test_enum_serialization(self):
        """Test that enums can be serialized to their values."""
        resource_type = ResourceType.LAMBDA_FUNCTION
        environment = Environment.PRODUCTION

        serialized = {
            "resource_type": resource_type.value,
            "environment": environment.value,
        }

        assert serialized["resource_type"] == "lambda_function"
        assert serialized["environment"] == "prod"

    def test_enum_deserialization(self):
        """Test that enums can be deserialized from their values."""
        data = {
            "resource_type": "rds_database",
            "environment": "staging",
        }

        resource_type = ResourceType(data["resource_type"])
        environment = Environment(data["environment"])

        assert resource_type == ResourceType.RDS_DATABASE
        assert environment == Environment.STAGING
