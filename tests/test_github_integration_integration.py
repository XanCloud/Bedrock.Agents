"""Integration tests for GitHubIntegration with a real GitHub repository.

These tests exercise the complete GitHub workflow end-to-end:
  authenticate → clone → create branch → commit → push → create PR

They are automatically skipped when the required environment variables are
not set, so they never block CI pipelines that lack credentials.

Required environment variables
-------------------------------
GITHUB_TOKEN   Personal-access token (or fine-grained token) with repo scope.
GITHUB_REPO    Full repository name in ``owner/repo`` format, e.g.
               ``my-org/iac-agent-test-repo``.

Optional environment variables
-------------------------------
GITHUB_ORG     Organisation or user name.  Defaults to the owner part of
               GITHUB_REPO when not set.
GITHUB_BASE_BRANCH
               The default branch to target for PRs.  Defaults to ``main``.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from datetime import datetime, timezone
from typing import Generator, Optional

import pytest

# ---------------------------------------------------------------------------
# Skip guard – evaluated once at collection time
# ---------------------------------------------------------------------------

_GITHUB_TOKEN: Optional[str] = os.environ.get("GITHUB_TOKEN")
_GITHUB_REPO: Optional[str] = os.environ.get("GITHUB_REPO")

_CREDS_AVAILABLE = bool(_GITHUB_TOKEN and _GITHUB_REPO)

_SKIP_REASON = (
    "Integration tests require GITHUB_TOKEN and GITHUB_REPO environment variables. "
    "Set them to run these tests against a real GitHub repository."
)

pytestmark = pytest.mark.skipif(not _CREDS_AVAILABLE, reason=_SKIP_REASON)

# ---------------------------------------------------------------------------
# Conditional imports (only needed when tests actually run)
# ---------------------------------------------------------------------------

if _CREDS_AVAILABLE:
    import git
    from github import Github

    from bedrock_iac_agent.github_integration import (
        GitHubIntegration,
        RetryStrategy,
    )
    from bedrock_iac_agent.models import (
        FileChange,
        GitHubCredentials,
        PullRequest,
        PullRequestDetails,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_owner_repo(full_name: str) -> tuple[str, str]:
    """Split ``owner/repo`` into a (owner, repo) tuple."""
    parts = full_name.split("/", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError(
            f"GITHUB_REPO must be in 'owner/repo' format, got: {full_name!r}"
        )
    return parts[0], parts[1]


def _unique_timestamp() -> str:
    """Return a timestamp string suitable for branch names."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def github_credentials() -> "GitHubCredentials":
    """Build GitHubCredentials from environment variables."""
    assert _GITHUB_TOKEN and _GITHUB_REPO  # already guarded by pytestmark
    owner, repo = _parse_owner_repo(_GITHUB_REPO)
    org = os.environ.get("GITHUB_ORG", owner)
    return GitHubCredentials(
        token=_GITHUB_TOKEN,
        organization=org,
        repository=repo,
    )


@pytest.fixture(scope="module")
def fast_retry() -> "RetryStrategy":
    """RetryStrategy with minimal delays for integration tests."""
    return RetryStrategy(max_attempts=3, base_delay=0.5, max_delay=2.0)


@pytest.fixture(scope="module")
def integration(
    github_credentials: "GitHubCredentials",
    fast_retry: "RetryStrategy",
) -> "GitHubIntegration":
    """Authenticated GitHubIntegration instance (module-scoped for speed)."""
    gh = GitHubIntegration(credentials=github_credentials, retry_strategy=fast_retry)
    gh.authenticate()
    return gh


@pytest.fixture(scope="module")
def base_branch() -> str:
    """The default branch to target for PRs."""
    return os.environ.get("GITHUB_BASE_BRANCH", "main")


@pytest.fixture(scope="module")
def repo_url(github_credentials: "GitHubCredentials") -> str:
    """HTTPS clone URL derived from credentials."""
    return (
        f"https://github.com/{github_credentials.organization}"
        f"/{github_credentials.repository}.git"
    )


@pytest.fixture()
def cloned_repo(
    integration: "GitHubIntegration",
    repo_url: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator["git.Repo", None, None]:
    """Clone the repository into a fresh temp directory; clean up after test."""
    local_path = str(tmp_path_factory.mktemp("iac-agent-clone-"))
    repo = integration.clone_repository(repo_url, local_path=local_path)
    yield repo
    # GitPython keeps file handles open; close before pytest cleans up tmp_path
    repo.close()


@pytest.fixture()
def branch_and_pr(
    integration: "GitHubIntegration",
    cloned_repo: "git.Repo",
    base_branch: str,
) -> Generator[tuple["git.Head", "PullRequest"], None, None]:
    """Create a branch, commit a file, push, open a PR; close PR on teardown.

    Yields (branch, pull_request) so individual tests can inspect both.
    """
    resource_type = "s3_bucket"
    environment = "dev"
    ts = _unique_timestamp()
    branch_name = GitHubIntegration.build_branch_name(resource_type, environment, ts)

    branch = integration.create_branch(cloned_repo, branch_name)

    file_change = FileChange(
        file_path=f"environments/{environment}/terraform.tfvars",
        content=(
            f'# Generated by integration test at {ts}\n'
            f'bucket_name = "iac-agent-test-{ts}"\n'
            f'environment = "{environment}"\n'
        ),
        operation="add",
    )
    commit_msg = (
        f"feat(s3): add iac-agent-test bucket for {environment} [{ts}]"
    )
    integration.commit_changes(cloned_repo, [file_change], commit_msg)
    integration.push_branch(cloned_repo, branch)

    pr_details = PullRequestDetails(
        title=f"feat(s3): add iac-agent-test bucket for {environment}",
        description="Integration test PR – safe to close",
        source_branch=branch_name,
        target_branch=base_branch,
        labels=["iac-agent", "integration-test"],
        reviewers=[],
        metadata={
            "request_id": f"req-inttest-{ts}",
            "conversation_id": f"conv-inttest-{ts}",
            "resource_type": resource_type,
            "environment": environment,
            "user_id": "integration-test@example.com",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "justification": "Automated integration test",
            "parameters": {
                "bucket_name": f"iac-agent-test-{ts}",
                "environment": environment,
            },
        },
    )
    pr = integration.create_pull_request(branch, pr_details)

    yield branch, pr

    # ---- Teardown: close the PR and delete the remote branch ----
    _close_pr_and_delete_branch(integration, pr, branch_name)


def _close_pr_and_delete_branch(
    integration: "GitHubIntegration",
    pr: "PullRequest",
    branch_name: str,
) -> None:
    """Best-effort cleanup: close the PR and delete the remote branch."""
    assert integration._github_repo is not None
    try:
        gh_pr = integration._github_repo.get_pull(pr.number)
        if gh_pr.state == "open":
            gh_pr.edit(state="closed")
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: log and continue so teardown doesn't mask test failures
        print(f"[teardown] Could not close PR #{pr.number}: {exc}")

    try:
        ref = integration._github_repo.get_git_ref(f"heads/{branch_name}")
        ref.delete()
    except Exception as exc:  # noqa: BLE001
        print(f"[teardown] Could not delete branch {branch_name!r}: {exc}")


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestAuthentication:
    """Requirement 5.2 – authenticate with secure credentials."""

    def test_authenticate_returns_true(self, github_credentials: "GitHubCredentials") -> None:
        """authenticate() returns True when credentials are valid."""
        gh = GitHubIntegration(credentials=github_credentials)
        result = gh.authenticate()
        assert result is True

    def test_authenticate_sets_github_client(self, github_credentials: "GitHubCredentials") -> None:
        """After authenticate(), _github_client and _github_repo are populated."""
        gh = GitHubIntegration(credentials=github_credentials)
        gh.authenticate()
        assert gh._github_client is not None
        assert gh._github_repo is not None

    def test_authenticate_invalid_token_raises(self) -> None:
        """Invalid token raises AuthenticationError."""
        from bedrock_iac_agent.github_integration import AuthenticationError

        assert _GITHUB_REPO is not None
        owner, repo = _parse_owner_repo(_GITHUB_REPO)
        bad_creds = GitHubCredentials(
            token="ghp_invalid_token_for_testing_only",
            organization=owner,
            repository=repo,
        )
        gh = GitHubIntegration(credentials=bad_creds)
        with pytest.raises(AuthenticationError):
            gh.authenticate()


class TestCloneRepository:
    """Requirement 5.1 – clone the base repository."""

    def test_clone_creates_local_repo(
        self,
        integration: "GitHubIntegration",
        repo_url: str,
        tmp_path: "os.PathLike[str]",
    ) -> None:
        """clone_repository() returns a valid git.Repo with a working tree."""
        local_path = str(tmp_path)
        repo = integration.clone_repository(repo_url, local_path=local_path)
        try:
            assert isinstance(repo, git.Repo)
            assert repo.working_tree_dir == local_path
            # The cloned repo should have at least one commit
            assert repo.head.commit is not None
        finally:
            repo.close()

    def test_clone_injects_token_into_url(
        self,
        integration: "GitHubIntegration",
        repo_url: str,
        tmp_path: "os.PathLike[str]",
    ) -> None:
        """The remote URL stored in the clone contains the auth token."""
        local_path = str(tmp_path)
        repo = integration.clone_repository(repo_url, local_path=local_path)
        try:
            origin_url = repo.remotes.origin.url
            assert _GITHUB_TOKEN is not None
            assert _GITHUB_TOKEN in origin_url
        finally:
            repo.close()


class TestBranchNaming:
    """Requirement 5.3 – branch naming pattern iac-agent/{resource-type}/{environment}/{timestamp}."""

    @pytest.mark.parametrize(
        "resource_type,environment",
        [
            ("s3_bucket", "dev"),
            ("ec2_instance", "prod"),
            ("lambda_function", "staging"),
            ("rds_database", "dev"),
        ],
    )
    def test_branch_name_pattern(self, resource_type: str, environment: str) -> None:
        """build_branch_name() produces the correct four-part pattern."""
        ts = "20240115-103000"
        name = GitHubIntegration.build_branch_name(resource_type, environment, ts)
        parts = name.split("/")
        assert len(parts) == 4, f"Expected 4 parts, got {len(parts)}: {name}"
        assert parts[0] == "iac-agent"
        assert parts[1] == resource_type.replace("_", "-").lower()
        assert parts[2] == environment.lower()
        assert parts[3] == ts

    def test_branch_name_timestamp_format(self) -> None:
        """Auto-generated timestamp follows YYYYMMDD-HHMMSS format."""
        name = GitHubIntegration.build_branch_name("vpc", "dev")
        ts_part = name.split("/")[-1]
        assert re.fullmatch(r"\d{8}-\d{6}", ts_part), (
            f"Timestamp part {ts_part!r} does not match YYYYMMDD-HHMMSS"
        )

    def test_all_twelve_resource_types(self) -> None:
        """All 12 Golden Module resource types produce valid branch names."""
        resource_types = [
            "s3_bucket", "ec2_instance", "rds_database", "lambda_function",
            "api_gateway", "dynamodb_table", "vpc", "security_group",
            "iam_role", "cloudwatch_log_group", "sns_topic", "sqs_queue",
        ]
        for rt in resource_types:
            name = GitHubIntegration.build_branch_name(rt, "dev", "20240115-103000")
            assert name.startswith("iac-agent/"), f"Bad prefix for {rt}: {name}"
            assert "/dev/" in name, f"Missing env segment for {rt}: {name}"


class TestCompleteWorkflow:
    """Requirements 5.1–5.5, 6.1–6.5 – full GitHub workflow end-to-end."""

    def test_pr_is_created(
        self, branch_and_pr: tuple["git.Head", "PullRequest"]
    ) -> None:
        """Requirement 6.1 – PR is created automatically when changes are pushed."""
        _, pr = branch_and_pr
        assert isinstance(pr, PullRequest)
        assert pr.number > 0
        assert pr.url.startswith("https://")

    def test_pr_url_is_accessible(
        self,
        integration: "GitHubIntegration",
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """The PR URL points to a real, open pull request."""
        _, pr = branch_and_pr
        assert integration._github_repo is not None
        gh_pr = integration._github_repo.get_pull(pr.number)
        assert gh_pr.state == "open"
        assert gh_pr.html_url == pr.url

    def test_pr_title_contains_resource_type_and_environment(
        self,
        integration: "GitHubIntegration",
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """Requirement 6.2 – PR title indicates resource type and environment."""
        _, pr = branch_and_pr
        assert integration._github_repo is not None
        gh_pr = integration._github_repo.get_pull(pr.number)
        title_lower = gh_pr.title.lower()
        assert "s3" in title_lower, f"Resource type missing from title: {gh_pr.title!r}"
        assert "dev" in title_lower, f"Environment missing from title: {gh_pr.title!r}"

    def test_pr_body_contains_resource_type(
        self,
        integration: "GitHubIntegration",
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """Requirement 6.3 – PR description includes resource type."""
        _, pr = branch_and_pr
        assert integration._github_repo is not None
        gh_pr = integration._github_repo.get_pull(pr.number)
        assert "s3_bucket" in gh_pr.body, (
            f"Resource type 's3_bucket' not found in PR body:\n{gh_pr.body}"
        )

    def test_pr_body_contains_environment(
        self,
        integration: "GitHubIntegration",
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """Requirement 6.3 – PR description includes environment."""
        _, pr = branch_and_pr
        assert integration._github_repo is not None
        gh_pr = integration._github_repo.get_pull(pr.number)
        assert "dev" in gh_pr.body, (
            f"Environment 'dev' not found in PR body:\n{gh_pr.body}"
        )

    def test_pr_body_contains_conversation_id(
        self,
        integration: "GitHubIntegration",
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """Requirement 6.4 – PR description references the original conversation."""
        _, pr = branch_and_pr
        assert integration._github_repo is not None
        gh_pr = integration._github_repo.get_pull(pr.number)
        assert "conv-inttest-" in gh_pr.body, (
            f"Conversation ID not found in PR body:\n{gh_pr.body}"
        )

    def test_pr_body_contains_parameter_table(
        self,
        integration: "GitHubIntegration",
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """Requirement 6.3 – PR description includes a configuration parameter table."""
        _, pr = branch_and_pr
        assert integration._github_repo is not None
        gh_pr = integration._github_repo.get_pull(pr.number)
        # The PR template renders a Markdown table with | Parameter | Value |
        assert "| Parameter | Value |" in gh_pr.body, (
            f"Parameter table not found in PR body:\n{gh_pr.body}"
        )

    def test_pr_body_matches_template_sections(
        self,
        integration: "GitHubIntegration",
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """PR body contains all expected template sections from the design doc."""
        _, pr = branch_and_pr
        assert integration._github_repo is not None
        gh_pr = integration._github_repo.get_pull(pr.number)
        body = gh_pr.body

        expected_sections = [
            "## Infrastructure Change Request",
            "**Resource Type**",
            "**Environment**",
            "**Requested By**",
            "**Timestamp**",
            "### Configuration Parameters",
            "### Changes",
            "### Justification",
            "### Review Checklist",
            "Generated by Bedrock IaC Agent",
            "Conversation ID:",
        ]
        for section in expected_sections:
            assert section in body, (
                f"Expected section {section!r} not found in PR body:\n{body}"
            )

    def test_branch_name_follows_naming_pattern(
        self,
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """Requirement 5.3 – pushed branch follows iac-agent/{resource-type}/{environment}/{timestamp}."""
        branch, _ = branch_and_pr
        name = branch.name
        assert re.fullmatch(
            r"iac-agent/[a-z0-9-]+/[a-z0-9-]+/\d{8}-\d{6}",
            name,
        ), f"Branch name {name!r} does not match expected pattern"

    def test_commit_message_contains_resource_type_and_environment(
        self,
        cloned_repo: "git.Repo",
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """Requirement 5.4 – commit message includes resource type and environment."""
        branch, _ = branch_and_pr
        # The branch fixture commits before yielding; inspect the HEAD commit
        commit_msg = cloned_repo.head.commit.message
        assert "s3" in commit_msg.lower(), (
            f"Resource type missing from commit message: {commit_msg!r}"
        )
        assert "dev" in commit_msg.lower(), (
            f"Environment missing from commit message: {commit_msg!r}"
        )

    def test_pr_branch_name_stored_in_result(
        self,
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """The returned PullRequest dataclass stores the correct branch name."""
        branch, pr = branch_and_pr
        assert pr.branch_name == branch.name

    def test_pr_created_at_is_recent(
        self,
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """The returned PullRequest has a recent created_at timestamp."""
        _, pr = branch_and_pr
        now = datetime.now(timezone.utc)
        age_seconds = (now - pr.created_at).total_seconds()
        # Allow up to 5 minutes for slow CI environments
        assert age_seconds < 300, (
            f"PR created_at is too old ({age_seconds:.0f}s ago): {pr.created_at}"
        )


class TestPRNotification:
    """Requirement 6.5 – agent informs user with the PR URL."""

    def test_pr_url_is_returned_to_caller(
        self,
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """create_pull_request() returns a PullRequest with a non-empty URL."""
        _, pr = branch_and_pr
        assert pr.url, "PR URL must not be empty"
        assert pr.url.startswith("https://github.com/"), (
            f"Unexpected PR URL format: {pr.url!r}"
        )

    def test_pr_number_is_positive(
        self,
        branch_and_pr: tuple["git.Head", "PullRequest"],
    ) -> None:
        """PR number is a positive integer (GitHub assigns sequential numbers)."""
        _, pr = branch_and_pr
        assert pr.number > 0


class TestRetryBehaviourIntegration:
    """Requirement 12.2 – network operations retry up to 3 times."""

    def test_retry_strategy_applied_on_push_failure(
        self,
        github_credentials: "GitHubCredentials",
        repo_url: str,
        tmp_path: "os.PathLike[str]",
    ) -> None:
        """push_branch() retries on transient git errors before raising NetworkError."""
        from unittest.mock import MagicMock, patch

        from bedrock_iac_agent.github_integration import NetworkError

        # Use zero-delay retry so the test is fast
        zero_retry = RetryStrategy(max_attempts=3, base_delay=0.0, max_delay=0.0)
        gh = GitHubIntegration(credentials=github_credentials, retry_strategy=zero_retry)
        gh.authenticate()

        local_path = str(tmp_path)
        repo = gh.clone_repository(repo_url, local_path=local_path)
        try:
            branch = gh.create_branch(repo, f"iac-agent/test/dev/{_unique_timestamp()}")

            push_call_count = 0

            def _failing_push(*args: object, **kwargs: object) -> None:
                nonlocal push_call_count
                push_call_count += 1
                raise git.GitCommandError("push", 128)

            with patch.object(repo.remote("origin"), "push", side_effect=_failing_push):
                with pytest.raises(NetworkError):
                    gh.push_branch(repo, branch)

            assert push_call_count == 3, (
                f"Expected 3 push attempts, got {push_call_count}"
            )
        finally:
            repo.close()
