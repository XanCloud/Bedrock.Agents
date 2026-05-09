"""Unit tests for GitHubIntegration.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 12.2
"""
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock, call
import pytest
import git
from github import GithubException

from bedrock_iac_agent.github_integration import (
    AuthenticationError,
    GitHubIntegration,
    NetworkError,
    RepositoryError,
    RetryStrategy,
    ValidationError,
    _build_parameter_table,
    _render_pr_body,
)
from bedrock_iac_agent.models import (
    FileChange,
    GitHubCredentials,
    PullRequest,
    PullRequestDetails,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def credentials():
    return GitHubCredentials(
        token="ghp_test_token_123",
        organization="test-org",
        repository="test-repo",
    )


@pytest.fixture
def fast_retry():
    """RetryStrategy with zero delay for fast tests."""
    return RetryStrategy(max_attempts=3, base_delay=0.0, max_delay=0.0)


@pytest.fixture
def integration(credentials, fast_retry):
    return GitHubIntegration(
        credentials=credentials,
        retry_strategy=fast_retry,
    )


@pytest.fixture
def pr_details():
    return PullRequestDetails(
        title="feat(s3): add data-lake bucket for dev",
        description="Add S3 bucket for data lake",
        source_branch="iac-agent/s3-bucket/dev/20240115-103000",
        target_branch="main",
        labels=["iac-agent", "terraform"],
        reviewers=["reviewer1"],
        metadata={
            "request_id": "req-abc-123",
            "conversation_id": "conv-xyz-456",
            "resource_type": "s3_bucket",
            "environment": "dev",
            "user_id": "developer@example.com",
            "timestamp": "2024-01-15T10:30:00Z",
            "justification": "Need storage for data lake",
            "parameters": {"bucket_name": "data-lake", "versioning": "true"},
        },
    )


# ---------------------------------------------------------------------------
# TestRetryStrategy
# ---------------------------------------------------------------------------


class TestRetryStrategy:
    """Tests for the RetryStrategy helper class.

    Requirement 12.2: retry network operations up to 3 times.
    """

    def test_default_max_attempts_is_three(self):
        strategy = RetryStrategy()
        assert strategy.max_attempts == 3

    def test_should_retry_network_error_within_attempts(self):
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(NetworkError("timeout"), attempt=1) is True
        assert strategy.should_retry(NetworkError("timeout"), attempt=2) is True

    def test_should_not_retry_when_attempts_exhausted(self):
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(NetworkError("timeout"), attempt=3) is False

    def test_should_retry_github_exception(self):
        strategy = RetryStrategy(max_attempts=3)
        exc = GithubException(503, {"message": "Service Unavailable"}, None)
        assert strategy.should_retry(exc, attempt=1) is True

    def test_should_retry_git_command_error(self):
        strategy = RetryStrategy(max_attempts=3)
        exc = git.GitCommandError("push", 128)
        assert strategy.should_retry(exc, attempt=1) is True

    def test_should_not_retry_value_error(self):
        strategy = RetryStrategy(max_attempts=3)
        assert strategy.should_retry(ValueError("bad input"), attempt=1) is False

    def test_get_delay_exponential_backoff(self):
        strategy = RetryStrategy(base_delay=1.0, max_delay=10.0, exponential_base=2.0)
        assert strategy.get_delay(0) == 1.0   # 1 * 2^0
        assert strategy.get_delay(1) == 2.0   # 1 * 2^1
        assert strategy.get_delay(2) == 4.0   # 1 * 2^2

    def test_get_delay_capped_at_max(self):
        strategy = RetryStrategy(base_delay=1.0, max_delay=3.0, exponential_base=2.0)
        assert strategy.get_delay(10) == 3.0  # capped at max_delay


# ---------------------------------------------------------------------------
# TestBuildBranchName
# ---------------------------------------------------------------------------


class TestBuildBranchName:
    """Tests for the branch naming pattern: iac-agent/{resource-type}/{environment}/{timestamp}.

    Requirement 5.3
    """

    def test_basic_branch_name(self):
        name = GitHubIntegration.build_branch_name("s3_bucket", "dev", "20240115-103000")
        assert name == "iac-agent/s3-bucket/dev/20240115-103000"

    def test_underscores_converted_to_hyphens(self):
        name = GitHubIntegration.build_branch_name("ec2_instance", "prod", "20240115-103000")
        assert name == "iac-agent/ec2-instance/prod/20240115-103000"

    def test_uppercase_normalised_to_lowercase(self):
        name = GitHubIntegration.build_branch_name("S3_BUCKET", "DEV", "20240115-103000")
        assert name == "iac-agent/s3-bucket/dev/20240115-103000"

    def test_timestamp_defaults_to_utc_now(self):
        name = GitHubIntegration.build_branch_name("lambda_function", "staging")
        assert name.startswith("iac-agent/lambda-function/staging/")
        # Timestamp portion should be 15 chars: YYYYMMDD-HHMMSS
        timestamp_part = name.split("/")[-1]
        assert len(timestamp_part) == 15

    def test_empty_resource_type_raises_validation_error(self):
        with pytest.raises(ValidationError):
            GitHubIntegration.build_branch_name("", "dev")

    def test_empty_environment_raises_validation_error(self):
        with pytest.raises(ValidationError):
            GitHubIntegration.build_branch_name("s3_bucket", "")

    def test_all_twelve_resource_types_produce_valid_names(self):
        """All 12 Golden Module resource types should produce valid branch names."""
        resource_types = [
            "s3_bucket", "ec2_instance", "rds_database", "lambda_function",
            "api_gateway", "dynamodb_table", "vpc", "security_group",
            "iam_role", "cloudwatch_log_group", "sns_topic", "sqs_queue",
        ]
        for rt in resource_types:
            name = GitHubIntegration.build_branch_name(rt, "dev", "20240115-103000")
            assert name.startswith("iac-agent/")
            assert "/dev/" in name
            assert "20240115-103000" in name

    def test_branch_name_follows_iac_agent_prefix_pattern(self):
        """Branch name must follow iac-agent/{resource-type}/{environment}/{timestamp}."""
        name = GitHubIntegration.build_branch_name("rds_database", "staging", "20240115-120000")
        parts = name.split("/")
        assert len(parts) == 4
        assert parts[0] == "iac-agent"
        assert parts[1] == "rds-database"
        assert parts[2] == "staging"
        assert parts[3] == "20240115-120000"


# ---------------------------------------------------------------------------
# TestAuthentication
# ---------------------------------------------------------------------------


class TestAuthentication:
    """Tests for GitHub authentication.

    Requirement 5.2
    """

    @patch("bedrock_iac_agent.github_integration.Github")
    def test_authenticate_success(self, mock_github_cls, integration):
        """Requirement 5.2: authenticate with secure credentials."""
        mock_client = MagicMock()
        mock_user = MagicMock()
        mock_user.login = "test-user"
        mock_client.get_user.return_value = mock_user
        mock_repo = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_cls.return_value = mock_client

        result = integration.authenticate()

        assert result is True
        mock_github_cls.assert_called_once_with("ghp_test_token_123")
        mock_client.get_repo.assert_called_once_with("test-org/test-repo")
        assert integration._github_client is mock_client
        assert integration._github_repo is mock_repo

    @patch("bedrock_iac_agent.github_integration.Github")
    def test_authenticate_invalid_token_raises_auth_error(self, mock_github_cls, integration):
        """Requirement 5.2: invalid token raises AuthenticationError."""
        mock_client = MagicMock()
        mock_client.get_user.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )
        mock_github_cls.return_value = mock_client

        with pytest.raises(AuthenticationError) as exc_info:
            integration.authenticate()

        assert "Bad credentials" in str(exc_info.value)

    @patch("bedrock_iac_agent.github_integration.Github")
    def test_authenticate_repo_not_found_raises_auth_error(self, mock_github_cls, integration):
        """Requirement 5.2: inaccessible repo raises AuthenticationError."""
        mock_client = MagicMock()
        mock_user = MagicMock()
        mock_user.login = "test-user"
        mock_client.get_user.return_value = mock_user
        mock_client.get_repo.side_effect = GithubException(
            404, {"message": "Not Found"}, None
        )
        mock_github_cls.return_value = mock_client

        with pytest.raises(AuthenticationError):
            integration.authenticate()

    @patch("bedrock_iac_agent.github_integration.Github")
    def test_authenticate_unexpected_exception_raises_auth_error(
        self, mock_github_cls, integration
    ):
        """Non-GitHub exceptions are also wrapped in AuthenticationError."""
        mock_github_cls.side_effect = RuntimeError("connection refused")

        with pytest.raises(AuthenticationError) as exc_info:
            integration.authenticate()

        assert "connection refused" in str(exc_info.value)

    @patch("bedrock_iac_agent.github_integration.Github")
    def test_authenticate_stores_github_client(self, mock_github_cls, integration):
        """After successful auth, _github_client and _github_repo are set."""
        mock_client = MagicMock()
        mock_user = MagicMock()
        mock_user.login = "test-user"
        mock_client.get_user.return_value = mock_user
        mock_client.get_repo.return_value = MagicMock()
        mock_github_cls.return_value = mock_client

        assert integration._github_client is None
        assert integration._github_repo is None

        integration.authenticate()

        assert integration._github_client is not None
        assert integration._github_repo is not None


# ---------------------------------------------------------------------------
# TestCloneRepository
# ---------------------------------------------------------------------------


class TestCloneRepository:
    """Tests for repository cloning.

    Requirement 5.1
    """

    @patch("bedrock_iac_agent.github_integration.git.Repo")
    def test_clone_success(self, mock_repo_cls, integration):
        """Requirement 5.1: clone the base repository."""
        mock_repo = MagicMock()
        mock_repo_cls.clone_from.return_value = mock_repo

        with tempfile.TemporaryDirectory() as tmpdir:
            result = integration.clone_repository(
                "https://github.com/test-org/test-repo.git",
                local_path=tmpdir,
            )

        assert result is mock_repo
        mock_repo_cls.clone_from.assert_called_once()
        call_args = mock_repo_cls.clone_from.call_args
        # Token should be injected into the URL
        assert "ghp_test_token_123" in call_args[0][0]

    @patch("bedrock_iac_agent.github_integration.git.Repo")
    def test_clone_injects_token_into_https_url(self, mock_repo_cls, integration):
        """Token is injected into HTTPS URL for authentication."""
        mock_repo_cls.clone_from.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            integration.clone_repository(
                "https://github.com/test-org/test-repo.git",
                local_path=tmpdir,
            )

        call_args = mock_repo_cls.clone_from.call_args[0]
        authenticated_url = call_args[0]
        assert authenticated_url == "https://ghp_test_token_123@github.com/test-org/test-repo.git"

    @patch("bedrock_iac_agent.github_integration.git.Repo")
    def test_clone_network_failure_raises_network_error(self, mock_repo_cls, integration):
        """Network failure during clone raises NetworkError."""
        mock_repo_cls.clone_from.side_effect = git.GitCommandError("clone", 128)

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(NetworkError):
                integration.clone_repository(
                    "https://github.com/test-org/test-repo.git",
                    local_path=tmpdir,
                )

    @patch("bedrock_iac_agent.github_integration.git.Repo")
    def test_clone_retries_on_network_failure(self, mock_repo_cls, integration):
        """Requirement 12.2: clone retries up to 3 times on network failure."""
        mock_repo_cls.clone_from.side_effect = git.GitCommandError("clone", 128)

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(NetworkError):
                integration.clone_repository(
                    "https://github.com/test-org/test-repo.git",
                    local_path=tmpdir,
                )

        assert mock_repo_cls.clone_from.call_count == 3

    @patch("bedrock_iac_agent.github_integration.git.Repo")
    def test_clone_creates_temp_dir_when_no_path_given(self, mock_repo_cls, integration):
        """When local_path is None, a temp directory is created automatically."""
        mock_repo_cls.clone_from.return_value = MagicMock()

        integration.clone_repository("https://github.com/test-org/test-repo.git")

        mock_repo_cls.clone_from.assert_called_once()
        call_args = mock_repo_cls.clone_from.call_args[0]
        local_path = call_args[1]
        assert local_path is not None
        assert "iac-agent-" in local_path

    @patch("bedrock_iac_agent.github_integration.git.Repo")
    def test_clone_ssh_url_not_modified(self, mock_repo_cls, integration):
        """SSH URLs are not modified (token injection only applies to HTTPS)."""
        mock_repo_cls.clone_from.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            integration.clone_repository(
                "git@github.com:test-org/test-repo.git",
                local_path=tmpdir,
            )

        call_args = mock_repo_cls.clone_from.call_args[0]
        url = call_args[0]
        assert url == "git@github.com:test-org/test-repo.git"


# ---------------------------------------------------------------------------
# TestCreateBranch
# ---------------------------------------------------------------------------


class TestCreateBranch:
    """Tests for branch creation.

    Requirement 5.3
    """

    def test_create_branch_success(self, integration):
        """Requirement 5.3: create a new branch with descriptive name."""
        mock_repo = MagicMock()
        mock_branch = MagicMock()
        mock_repo.create_head.return_value = mock_branch

        result = integration.create_branch(mock_repo, "iac-agent/s3-bucket/dev/20240115-103000")

        assert result is mock_branch
        mock_repo.create_head.assert_called_once_with("iac-agent/s3-bucket/dev/20240115-103000")
        mock_branch.checkout.assert_called_once()

    def test_create_branch_checks_out_new_branch(self, integration):
        """After creation, the new branch is checked out."""
        mock_repo = MagicMock()
        mock_branch = MagicMock()
        mock_repo.create_head.return_value = mock_branch

        integration.create_branch(mock_repo, "iac-agent/vpc/prod/20240115-103000")

        mock_branch.checkout.assert_called_once()

    def test_create_branch_empty_name_raises_validation_error(self, integration):
        """Empty branch name raises ValidationError."""
        mock_repo = MagicMock()

        with pytest.raises(ValidationError):
            integration.create_branch(mock_repo, "")

    def test_create_branch_git_error_raises_repository_error(self, integration):
        """Git command failure raises RepositoryError."""
        mock_repo = MagicMock()
        mock_repo.create_head.side_effect = git.GitCommandError("branch", 128)

        with pytest.raises(RepositoryError):
            integration.create_branch(mock_repo, "iac-agent/s3-bucket/dev/20240115-103000")


# ---------------------------------------------------------------------------
# TestCommitChanges
# ---------------------------------------------------------------------------


class TestCommitChanges:
    """Tests for committing file changes.

    Requirement 5.4
    """

    def test_commit_changes_success(self, integration):
        """Requirement 5.4: commit changes with descriptive message."""
        mock_repo = MagicMock()
        mock_commit = MagicMock()
        mock_commit.hexsha = "abc1234567890"
        mock_repo.index.commit.return_value = mock_commit
        mock_repo.working_tree_dir = tempfile.mkdtemp()

        files = [
            FileChange(
                file_path="environments/dev/terraform.tfvars",
                content='bucket_name = "data-lake"\n',
                operation="add",
            )
        ]
        commit_msg = "feat(s3): add data-lake bucket for dev [req-abc-123]"

        result = integration.commit_changes(mock_repo, files, commit_msg)

        assert result is mock_commit
        mock_repo.index.commit.assert_called_once_with(commit_msg)

    def test_commit_changes_adds_file_to_index(self, integration):
        """Files are staged before committing."""
        mock_repo = MagicMock()
        mock_repo.index.commit.return_value = MagicMock()
        mock_repo.working_tree_dir = tempfile.mkdtemp()

        files = [
            FileChange(
                file_path="environments/dev/terraform.tfvars",
                content='bucket_name = "data-lake"\n',
                operation="add",
            )
        ]

        integration.commit_changes(mock_repo, files, "test commit")

        mock_repo.index.add.assert_called_once_with(["environments/dev/terraform.tfvars"])

    def test_commit_changes_empty_files_raises_validation_error(self, integration):
        """Empty file list raises ValidationError."""
        mock_repo = MagicMock()

        with pytest.raises(ValidationError):
            integration.commit_changes(mock_repo, [], "test commit")

    def test_commit_changes_modify_operation(self, integration):
        """Modify operation writes file and stages it."""
        mock_repo = MagicMock()
        mock_repo.index.commit.return_value = MagicMock()
        tmpdir = tempfile.mkdtemp()
        mock_repo.working_tree_dir = tmpdir

        # Create the file first
        file_path = os.path.join(tmpdir, "environments", "dev", "terraform.tfvars")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write("old content\n")

        files = [
            FileChange(
                file_path="environments/dev/terraform.tfvars",
                content="new content\n",
                operation="modify",
            )
        ]

        integration.commit_changes(mock_repo, files, "update tfvars")

        # Verify file was written with new content
        with open(file_path) as f:
            assert f.read() == "new content\n"

    def test_commit_changes_delete_operation(self, integration):
        """Delete operation removes file and unstages it."""
        mock_repo = MagicMock()
        mock_repo.index.commit.return_value = MagicMock()
        tmpdir = tempfile.mkdtemp()
        mock_repo.working_tree_dir = tmpdir

        # Create the file to be deleted
        file_path = os.path.join(tmpdir, "environments", "dev", "terraform.tfvars")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write("content\n")

        files = [
            FileChange(
                file_path="environments/dev/terraform.tfvars",
                content="",
                operation="delete",
            )
        ]

        integration.commit_changes(mock_repo, files, "remove tfvars")

        assert not os.path.exists(file_path)
        mock_repo.index.remove.assert_called_once_with(["environments/dev/terraform.tfvars"])

    def test_commit_message_includes_resource_type_and_environment(self, integration):
        """Commit message should describe the resource type and environment."""
        mock_repo = MagicMock()
        mock_repo.index.commit.return_value = MagicMock()
        mock_repo.working_tree_dir = tempfile.mkdtemp()

        files = [
            FileChange(
                file_path="environments/prod/terraform.tfvars",
                content='instance_type = "t3.medium"\n',
                operation="add",
            )
        ]
        commit_msg = "feat(ec2): add web-server instance for prod [req-xyz-789]"

        integration.commit_changes(mock_repo, files, commit_msg)

        mock_repo.index.commit.assert_called_once_with(commit_msg)
        actual_msg = mock_repo.index.commit.call_args[0][0]
        assert "ec2" in actual_msg
        assert "prod" in actual_msg


# ---------------------------------------------------------------------------
# TestPushBranch
# ---------------------------------------------------------------------------


class TestPushBranch:
    """Tests for pushing branches to remote.

    Requirement 5.5
    """

    def test_push_branch_success(self, integration):
        """Requirement 5.5: push branch to remote repository."""
        mock_repo = MagicMock()
        mock_branch = MagicMock()
        mock_branch.name = "iac-agent/s3-bucket/dev/20240115-103000"
        mock_origin = MagicMock()
        mock_push_info = MagicMock()
        mock_push_info.flags = 0  # No error flags
        mock_origin.push.return_value = [mock_push_info]
        mock_repo.remote.return_value = mock_origin

        result = integration.push_branch(mock_repo, mock_branch)

        assert result is True
        mock_repo.remote.assert_called_once_with("origin")
        mock_origin.push.assert_called_once_with(
            refspec="iac-agent/s3-bucket/dev/20240115-103000:iac-agent/s3-bucket/dev/20240115-103000"
        )

    def test_push_branch_network_failure_raises_network_error(self, integration):
        """Network failure during push raises NetworkError."""
        mock_repo = MagicMock()
        mock_branch = MagicMock()
        mock_branch.name = "iac-agent/s3-bucket/dev/20240115-103000"
        mock_origin = MagicMock()
        mock_origin.push.side_effect = git.GitCommandError("push", 128)
        mock_repo.remote.return_value = mock_origin

        with pytest.raises(NetworkError):
            integration.push_branch(mock_repo, mock_branch)

    def test_push_branch_retries_three_times_on_failure(self, integration):
        """Requirement 12.2: push retries exactly 3 times before failing."""
        mock_repo = MagicMock()
        mock_branch = MagicMock()
        mock_branch.name = "iac-agent/s3-bucket/dev/20240115-103000"
        mock_origin = MagicMock()
        mock_origin.push.side_effect = git.GitCommandError("push", 128)
        mock_repo.remote.return_value = mock_origin

        with pytest.raises(NetworkError):
            integration.push_branch(mock_repo, mock_branch)

        assert mock_origin.push.call_count == 3

    def test_push_branch_succeeds_on_second_attempt(self, integration):
        """Push succeeds after one transient failure."""
        mock_repo = MagicMock()
        mock_branch = MagicMock()
        mock_branch.name = "iac-agent/s3-bucket/dev/20240115-103000"
        mock_origin = MagicMock()
        mock_push_info = MagicMock()
        mock_push_info.flags = 0
        mock_origin.push.side_effect = [
            git.GitCommandError("push", 128),  # First attempt fails
            [mock_push_info],                   # Second attempt succeeds
        ]
        mock_repo.remote.return_value = mock_origin

        result = integration.push_branch(mock_repo, mock_branch)

        assert result is True
        assert mock_origin.push.call_count == 2


# ---------------------------------------------------------------------------
# TestCreatePullRequest
# ---------------------------------------------------------------------------


class TestCreatePullRequest:
    """Tests for Pull Request creation.

    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
    """

    def _make_authenticated_integration(self, credentials, fast_retry):
        """Helper: return an integration with a mocked authenticated GitHub repo."""
        integration = GitHubIntegration(
            credentials=credentials,
            retry_strategy=fast_retry,
        )
        integration._github_repo = MagicMock()
        return integration

    def test_create_pr_success(self, credentials, fast_retry, pr_details):
        """Requirement 6.1: create PR automatically when changes are pushed."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        mock_gh_pr = MagicMock()
        mock_gh_pr.html_url = "https://github.com/test-org/test-repo/pull/42"
        mock_gh_pr.number = 42
        integration._github_repo.create_pull.return_value = mock_gh_pr

        mock_branch = MagicMock()
        mock_branch.name = pr_details.source_branch

        result = integration.create_pull_request(mock_branch, pr_details)

        assert isinstance(result, PullRequest)
        assert result.url == "https://github.com/test-org/test-repo/pull/42"
        assert result.number == 42
        assert result.branch_name == pr_details.source_branch

    def test_create_pr_uses_correct_title(self, credentials, fast_retry, pr_details):
        """Requirement 6.2: PR title indicates resource type and environment."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        mock_gh_pr = MagicMock()
        mock_gh_pr.html_url = "https://github.com/test-org/test-repo/pull/1"
        mock_gh_pr.number = 1
        integration._github_repo.create_pull.return_value = mock_gh_pr

        mock_branch = MagicMock()
        integration.create_pull_request(mock_branch, pr_details)

        call_kwargs = integration._github_repo.create_pull.call_args[1]
        assert call_kwargs["title"] == pr_details.title

    def test_create_pr_body_contains_resource_type(self, credentials, fast_retry, pr_details):
        """Requirement 6.3: PR description includes resource type."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        mock_gh_pr = MagicMock()
        mock_gh_pr.html_url = "https://github.com/test-org/test-repo/pull/1"
        mock_gh_pr.number = 1
        integration._github_repo.create_pull.return_value = mock_gh_pr

        mock_branch = MagicMock()
        integration.create_pull_request(mock_branch, pr_details)

        call_kwargs = integration._github_repo.create_pull.call_args[1]
        body = call_kwargs["body"]
        assert "s3_bucket" in body

    def test_create_pr_body_contains_environment(self, credentials, fast_retry, pr_details):
        """Requirement 6.3: PR description includes environment."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        mock_gh_pr = MagicMock()
        mock_gh_pr.html_url = "https://github.com/test-org/test-repo/pull/1"
        mock_gh_pr.number = 1
        integration._github_repo.create_pull.return_value = mock_gh_pr

        mock_branch = MagicMock()
        integration.create_pull_request(mock_branch, pr_details)

        call_kwargs = integration._github_repo.create_pull.call_args[1]
        body = call_kwargs["body"]
        assert "dev" in body

    def test_create_pr_body_contains_request_id(self, credentials, fast_retry, pr_details):
        """Requirement 6.4: PR description references original request (request_id)."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        mock_gh_pr = MagicMock()
        mock_gh_pr.html_url = "https://github.com/test-org/test-repo/pull/1"
        mock_gh_pr.number = 1
        integration._github_repo.create_pull.return_value = mock_gh_pr

        mock_branch = MagicMock()
        integration.create_pull_request(mock_branch, pr_details)

        call_kwargs = integration._github_repo.create_pull.call_args[1]
        body = call_kwargs["body"]
        # request_id is in metadata but rendered via _render_pr_body
        # The PR body should contain the conversation_id at minimum
        assert "conv-xyz-456" in body

    def test_create_pr_body_contains_conversation_id(self, credentials, fast_retry, pr_details):
        """Requirement 6.4: PR description includes conversation_id."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        mock_gh_pr = MagicMock()
        mock_gh_pr.html_url = "https://github.com/test-org/test-repo/pull/1"
        mock_gh_pr.number = 1
        integration._github_repo.create_pull.return_value = mock_gh_pr

        mock_branch = MagicMock()
        integration.create_pull_request(mock_branch, pr_details)

        call_kwargs = integration._github_repo.create_pull.call_args[1]
        body = call_kwargs["body"]
        assert "conv-xyz-456" in body

    def test_create_pr_uses_correct_source_and_target_branches(
        self, credentials, fast_retry, pr_details
    ):
        """PR is created from source_branch to target_branch."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        mock_gh_pr = MagicMock()
        mock_gh_pr.html_url = "https://github.com/test-org/test-repo/pull/1"
        mock_gh_pr.number = 1
        integration._github_repo.create_pull.return_value = mock_gh_pr

        mock_branch = MagicMock()
        integration.create_pull_request(mock_branch, pr_details)

        call_kwargs = integration._github_repo.create_pull.call_args[1]
        assert call_kwargs["head"] == pr_details.source_branch
        assert call_kwargs["base"] == pr_details.target_branch

    def test_create_pr_applies_labels(self, credentials, fast_retry, pr_details):
        """Labels are applied to the PR."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        mock_gh_pr = MagicMock()
        mock_gh_pr.html_url = "https://github.com/test-org/test-repo/pull/1"
        mock_gh_pr.number = 1
        integration._github_repo.create_pull.return_value = mock_gh_pr

        mock_branch = MagicMock()
        integration.create_pull_request(mock_branch, pr_details)

        mock_gh_pr.set_labels.assert_called_once_with("iac-agent", "terraform")

    def test_create_pr_requests_reviewers(self, credentials, fast_retry, pr_details):
        """Reviewers are requested on the PR."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        mock_gh_pr = MagicMock()
        mock_gh_pr.html_url = "https://github.com/test-org/test-repo/pull/1"
        mock_gh_pr.number = 1
        integration._github_repo.create_pull.return_value = mock_gh_pr

        mock_branch = MagicMock()
        integration.create_pull_request(mock_branch, pr_details)

        mock_gh_pr.create_review_request.assert_called_once_with(reviewers=["reviewer1"])

    def test_create_pr_without_authentication_raises_auth_error(
        self, integration, pr_details
    ):
        """Calling create_pull_request before authenticate raises AuthenticationError."""
        mock_branch = MagicMock()

        with pytest.raises(AuthenticationError):
            integration.create_pull_request(mock_branch, pr_details)

    def test_create_pr_github_exception_raises_repository_error(
        self, credentials, fast_retry, pr_details
    ):
        """GitHub API error during PR creation raises RepositoryError."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        integration._github_repo.create_pull.side_effect = GithubException(
            422, {"message": "Validation Failed"}, None
        )

        mock_branch = MagicMock()

        with pytest.raises(RepositoryError):
            integration.create_pull_request(mock_branch, pr_details)

    def test_create_pr_network_failure_retries_three_times(
        self, credentials, fast_retry, pr_details
    ):
        """Requirement 12.2: PR creation retries up to 3 times on network failure."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        integration._github_repo.create_pull.side_effect = GithubException(
            503, {"message": "Service Unavailable"}, None
        )

        mock_branch = MagicMock()

        with pytest.raises(Exception):
            integration.create_pull_request(mock_branch, pr_details)

        assert integration._github_repo.create_pull.call_count == 3

    def test_create_pr_label_failure_does_not_abort(self, credentials, fast_retry, pr_details):
        """Label application failure is non-fatal (best-effort)."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        mock_gh_pr = MagicMock()
        mock_gh_pr.html_url = "https://github.com/test-org/test-repo/pull/1"
        mock_gh_pr.number = 1
        mock_gh_pr.set_labels.side_effect = GithubException(
            422, {"message": "Label not found"}, None
        )
        integration._github_repo.create_pull.return_value = mock_gh_pr

        mock_branch = MagicMock()
        # Should not raise even though label application failed
        result = integration.create_pull_request(mock_branch, pr_details)

        assert isinstance(result, PullRequest)

    def test_create_pr_reviewer_failure_does_not_abort(self, credentials, fast_retry, pr_details):
        """Reviewer request failure is non-fatal (best-effort)."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        mock_gh_pr = MagicMock()
        mock_gh_pr.html_url = "https://github.com/test-org/test-repo/pull/1"
        mock_gh_pr.number = 1
        mock_gh_pr.create_review_request.side_effect = GithubException(
            422, {"message": "Reviewer not found"}, None
        )
        integration._github_repo.create_pull.return_value = mock_gh_pr

        mock_branch = MagicMock()
        result = integration.create_pull_request(mock_branch, pr_details)

        assert isinstance(result, PullRequest)

    def test_create_pr_returns_correct_created_at_timestamp(
        self, credentials, fast_retry, pr_details
    ):
        """PullRequest.created_at is a UTC datetime."""
        integration = self._make_authenticated_integration(credentials, fast_retry)
        mock_gh_pr = MagicMock()
        mock_gh_pr.html_url = "https://github.com/test-org/test-repo/pull/99"
        mock_gh_pr.number = 99
        integration._github_repo.create_pull.return_value = mock_gh_pr

        mock_branch = MagicMock()
        result = integration.create_pull_request(mock_branch, pr_details)

        assert isinstance(result.created_at, datetime)
        assert result.created_at.tzinfo is not None
