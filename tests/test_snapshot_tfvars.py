"""
Snapshot tests for tfvars generation.

Each test generates a tfvars file for a specific (resource_type, environment)
combination and compares it against a stored golden snapshot.

Regenerating snapshots
----------------------
Set the environment variable UPDATE_SNAPSHOTS=1 before running pytest to
overwrite the stored snapshots with the current generator output:

    UPDATE_SNAPSHOTS=1 venv/bin/pytest tests/test_snapshot_tfvars.py -v

Requirements covered: 3.1, 3.5
"""

import os
from datetime import datetime
from pathlib import Path

import pytest

from src.bedrock_iac_agent import (
    ConfigurationGenerator,
    Environment,
    GoldenModulesInventory,
    NamingConventions,
    ResourceType,
    StructuredRequest,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
UPDATE_SNAPSHOTS = os.environ.get("UPDATE_SNAPSHOTS", "0") == "1"

# Fixed timestamp so snapshots are deterministic
FIXED_TIMESTAMP = datetime(2024, 1, 15, 10, 30, 0)

# Standard naming conventions used across all snapshot tests
STANDARD_NAMING = NamingConventions(
    prefix="mycompany",
    environment_suffix=True,
    separator="-",
    max_length=63,
    allowed_characters=r"[a-z0-9\-]",
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

INVENTORY = GoldenModulesInventory()


def _make_request(
    resource_type: ResourceType,
    parameters: dict,
    environment: Environment,
    request_id: str = "req-snapshot-001",
    justification: str = "Snapshot test request",
) -> StructuredRequest:
    """Build a deterministic StructuredRequest for snapshot generation."""
    return StructuredRequest(
        resource_type=resource_type,
        parameters=parameters,
        environment=environment,
        confidence=1.0,
        user_justification=justification,
        request_id=request_id,
        timestamp=FIXED_TIMESTAMP,
    )


def _snapshot_path(resource_type: ResourceType, environment: Environment) -> Path:
    """Return the path to the snapshot file for a given resource/environment pair."""
    return SNAPSHOTS_DIR / f"{resource_type.value}__{environment.value}.tfvars"


def _assert_matches_snapshot(
    content: str,
    resource_type: ResourceType,
    environment: Environment,
) -> None:
    """
    Compare *content* against the stored snapshot.

    If UPDATE_SNAPSHOTS is set, write the new content to disk instead of
    asserting equality.
    """
    path = _snapshot_path(resource_type, environment)

    if UPDATE_SNAPSHOTS:
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return  # nothing to assert when regenerating

    assert path.exists(), (
        f"Snapshot file not found: {path}\n"
        "Run with UPDATE_SNAPSHOTS=1 to generate it."
    )
    expected = path.read_text(encoding="utf-8")
    assert content == expected, (
        f"Snapshot mismatch for {resource_type.value} / {environment.value}.\n"
        "If this change is intentional, regenerate snapshots with UPDATE_SNAPSHOTS=1."
    )


# ---------------------------------------------------------------------------
# Parametrised snapshot test cases
# ---------------------------------------------------------------------------

# Each entry: (resource_type, environment, parameters, request_id)
SNAPSHOT_CASES = [
    # S3 Bucket
    (
        ResourceType.S3_BUCKET,
        Environment.DEVELOPMENT,
        {"bucket_name": "data-lake"},
        "req-s3-dev",
    ),
    (
        ResourceType.S3_BUCKET,
        Environment.STAGING,
        {"bucket_name": "data-lake"},
        "req-s3-staging",
    ),
    (
        ResourceType.S3_BUCKET,
        Environment.PRODUCTION,
        {"bucket_name": "data-lake"},
        "req-s3-prod",
    ),
    # EC2 Instance
    (
        ResourceType.EC2_INSTANCE,
        Environment.DEVELOPMENT,
        {"instance_name": "web-server", "instance_type": "t3.micro"},
        "req-ec2-dev",
    ),
    (
        ResourceType.EC2_INSTANCE,
        Environment.PRODUCTION,
        {"instance_name": "web-server", "instance_type": "t3.large"},
        "req-ec2-prod",
    ),
    # RDS Database
    (
        ResourceType.RDS_DATABASE,
        Environment.DEVELOPMENT,
        {"db_name": "appdb", "engine": "postgres"},
        "req-rds-dev",
    ),
    (
        ResourceType.RDS_DATABASE,
        Environment.PRODUCTION,
        {"db_name": "appdb", "engine": "postgres", "instance_class": "db.r6g.large"},
        "req-rds-prod",
    ),
    # Lambda Function
    (
        ResourceType.LAMBDA_FUNCTION,
        Environment.DEVELOPMENT,
        {"function_name": "data-processor", "runtime": "python3.11"},
        "req-lambda-dev",
    ),
    (
        ResourceType.LAMBDA_FUNCTION,
        Environment.PRODUCTION,
        {
            "function_name": "data-processor",
            "runtime": "python3.11",
            "memory_size": 512,
            "timeout": 60,
        },
        "req-lambda-prod",
    ),
    # API Gateway
    (
        ResourceType.API_GATEWAY,
        Environment.DEVELOPMENT,
        {"api_name": "rest-api"},
        "req-apigw-dev",
    ),
    # DynamoDB Table
    (
        ResourceType.DYNAMODB_TABLE,
        Environment.DEVELOPMENT,
        {"table_name": "sessions", "hash_key": "id"},
        "req-dynamo-dev",
    ),
    # VPC
    (
        ResourceType.VPC,
        Environment.DEVELOPMENT,
        {"vpc_name": "main", "cidr_block": "10.0.0.0/16"},
        "req-vpc-dev",
    ),
    # Security Group
    (
        ResourceType.SECURITY_GROUP,
        Environment.DEVELOPMENT,
        {"security_group_name": "app-sg", "vpc_id": "vpc-12345678"},
        "req-sg-dev",
    ),
    # IAM Role
    (
        ResourceType.IAM_ROLE,
        Environment.DEVELOPMENT,
        {"role_name": "lambda-exec", "trusted_services": ["lambda.amazonaws.com"]},
        "req-iam-dev",
    ),
    # CloudWatch Log Group
    (
        ResourceType.CLOUDWATCH_LOG_GROUP,
        Environment.DEVELOPMENT,
        {"log_group_name": "app-logs"},
        "req-cw-dev",
    ),
    # SNS Topic
    (
        ResourceType.SNS_TOPIC,
        Environment.DEVELOPMENT,
        {"topic_name": "alerts"},
        "req-sns-dev",
    ),
    # SQS Queue
    (
        ResourceType.SQS_QUEUE,
        Environment.DEVELOPMENT,
        {"queue_name": "job-queue"},
        "req-sqs-dev",
    ),
]


@pytest.mark.parametrize(
    "resource_type, environment, parameters, request_id",
    SNAPSHOT_CASES,
    ids=[
        f"{rt.value}__{env.value}"
        for rt, env, _, _ in SNAPSHOT_CASES
    ],
)
def test_tfvars_matches_snapshot(
    resource_type: ResourceType,
    environment: Environment,
    parameters: dict,
    request_id: str,
) -> None:
    """
    Generated tfvars content must match the stored golden snapshot.

    Requirements: 3.1 (valid tfvars generated), 3.5 (valid HCL syntax).
    """
    generator = ConfigurationGenerator()
    schema = INVENTORY.get_module_schema(resource_type)
    request = _make_request(resource_type, parameters, environment, request_id)

    result = generator.generate_tfvars(request, schema, naming_conventions=STANDARD_NAMING)

    _assert_matches_snapshot(result.content, resource_type, environment)


# ---------------------------------------------------------------------------
# Snapshot content invariants
# ---------------------------------------------------------------------------


class TestSnapshotInvariants:
    """
    Verify structural invariants that every snapshot must satisfy.

    These tests run against the *live* generator output (not the stored files)
    so they catch regressions even before snapshots are regenerated.
    """

    @pytest.mark.parametrize(
        "resource_type, environment, parameters, request_id",
        SNAPSHOT_CASES,
        ids=[
            f"{rt.value}__{env.value}"
            for rt, env, _, _ in SNAPSHOT_CASES
        ],
    )
    def test_snapshot_starts_with_comment_header(
        self,
        resource_type: ResourceType,
        environment: Environment,
        parameters: dict,
        request_id: str,
    ) -> None:
        """Every generated tfvars must begin with the agent comment header (Req 3.5)."""
        generator = ConfigurationGenerator()
        schema = INVENTORY.get_module_schema(resource_type)
        request = _make_request(resource_type, parameters, environment, request_id)
        result = generator.generate_tfvars(request, schema, naming_conventions=STANDARD_NAMING)

        assert result.content.startswith("#"), (
            f"tfvars for {resource_type.value}/{environment.value} must start with a comment header"
        )

    @pytest.mark.parametrize(
        "resource_type, environment, parameters, request_id",
        SNAPSHOT_CASES,
        ids=[
            f"{rt.value}__{env.value}"
            for rt, env, _, _ in SNAPSHOT_CASES
        ],
    )
    def test_snapshot_contains_environment_assignment(
        self,
        resource_type: ResourceType,
        environment: Environment,
        parameters: dict,
        request_id: str,
    ) -> None:
        """Every snapshot must contain an environment = "..." assignment (Req 3.1)."""
        generator = ConfigurationGenerator()
        schema = INVENTORY.get_module_schema(resource_type)
        request = _make_request(resource_type, parameters, environment, request_id)
        result = generator.generate_tfvars(request, schema, naming_conventions=STANDARD_NAMING)

        assert f'environment = "{environment.value}"' in result.content, (
            f"Missing environment assignment in {resource_type.value}/{environment.value} snapshot"
        )

    @pytest.mark.parametrize(
        "resource_type, environment, parameters, request_id",
        SNAPSHOT_CASES,
        ids=[
            f"{rt.value}__{env.value}"
            for rt, env, _, _ in SNAPSHOT_CASES
        ],
    )
    def test_snapshot_uses_hcl_assignment_syntax(
        self,
        resource_type: ResourceType,
        environment: Environment,
        parameters: dict,
        request_id: str,
    ) -> None:
        """Every snapshot must use HCL key = value syntax (Req 3.5)."""
        generator = ConfigurationGenerator()
        schema = INVENTORY.get_module_schema(resource_type)
        request = _make_request(resource_type, parameters, environment, request_id)
        result = generator.generate_tfvars(request, schema, naming_conventions=STANDARD_NAMING)

        # Strip comment lines and check that at least one assignment exists
        non_comment_lines = [
            line for line in result.content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert any(" = " in line for line in non_comment_lines), (
            f"No HCL assignment found in {resource_type.value}/{environment.value} snapshot"
        )

    @pytest.mark.parametrize(
        "resource_type, environment, parameters, request_id",
        SNAPSHOT_CASES,
        ids=[
            f"{rt.value}__{env.value}"
            for rt, env, _, _ in SNAPSHOT_CASES
        ],
    )
    def test_snapshot_ends_with_newline(
        self,
        resource_type: ResourceType,
        environment: Environment,
        parameters: dict,
        request_id: str,
    ) -> None:
        """Every snapshot must end with a newline (standard text-file convention)."""
        generator = ConfigurationGenerator()
        schema = INVENTORY.get_module_schema(resource_type)
        request = _make_request(resource_type, parameters, environment, request_id)
        result = generator.generate_tfvars(request, schema, naming_conventions=STANDARD_NAMING)

        assert result.content.endswith("\n"), (
            f"tfvars for {resource_type.value}/{environment.value} must end with a newline"
        )

    @pytest.mark.parametrize(
        "resource_type, environment, parameters, request_id",
        SNAPSHOT_CASES,
        ids=[
            f"{rt.value}__{env.value}"
            for rt, env, _, _ in SNAPSHOT_CASES
        ],
    )
    def test_snapshot_naming_convention_applied(
        self,
        resource_type: ResourceType,
        environment: Environment,
        parameters: dict,
        request_id: str,
    ) -> None:
        """
        The 'mycompany' prefix and environment suffix must appear in name-like
        parameters (Req 3.3 — naming conventions applied at runtime).
        """
        generator = ConfigurationGenerator()
        schema = INVENTORY.get_module_schema(resource_type)
        request = _make_request(resource_type, parameters, environment, request_id)
        result = generator.generate_tfvars(request, schema, naming_conventions=STANDARD_NAMING)

        # Check that at least one name-like value contains the prefix
        assert "mycompany" in result.content, (
            f"Naming convention prefix 'mycompany' not found in "
            f"{resource_type.value}/{environment.value} snapshot"
        )


# ---------------------------------------------------------------------------
# Snapshot file existence check
# ---------------------------------------------------------------------------


class TestSnapshotFilesExist:
    """Verify that every expected snapshot file is present on disk."""

    @pytest.mark.parametrize(
        "resource_type, environment",
        [(rt, env) for rt, env, _, _ in SNAPSHOT_CASES],
        ids=[f"{rt.value}__{env.value}" for rt, env, _, _ in SNAPSHOT_CASES],
    )
    def test_snapshot_file_exists(
        self,
        resource_type: ResourceType,
        environment: Environment,
    ) -> None:
        """Each snapshot file must exist in tests/snapshots/."""
        path = _snapshot_path(resource_type, environment)
        assert path.exists(), (
            f"Snapshot file missing: {path}\n"
            "Run with UPDATE_SNAPSHOTS=1 to generate it."
        )

    @pytest.mark.parametrize(
        "resource_type, environment",
        [(rt, env) for rt, env, _, _ in SNAPSHOT_CASES],
        ids=[f"{rt.value}__{env.value}" for rt, env, _, _ in SNAPSHOT_CASES],
    )
    def test_snapshot_file_is_non_empty(
        self,
        resource_type: ResourceType,
        environment: Environment,
    ) -> None:
        """Each snapshot file must be non-empty."""
        path = _snapshot_path(resource_type, environment)
        if not path.exists():
            pytest.skip(f"Snapshot not yet generated: {path}")
        assert path.stat().st_size > 0, f"Snapshot file is empty: {path}"
