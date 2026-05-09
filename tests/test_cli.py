"""Unit tests for the CLIInterface class.

Tests cover:
- CLIInterface instantiation
- send_message() routing to the agent
- display_progress() output formatting
- exit_session() state management
- start_session() REPL loop (with mocked input)
- Error handling paths

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

from __future__ import annotations

import uuid
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from bedrock_iac_agent.cli import CLIInterface, ProgressIndicator
from bedrock_iac_agent.models import AgentResponse, ConversationContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_agent(response_message: str = "PR created: https://github.com/org/repo/pull/1") -> MagicMock:
    """Return a mock BedrockIaCAgent that returns a canned AgentResponse."""
    from bedrock_iac_agent.agent import BedrockIaCAgent

    agent = MagicMock(spec=BedrockIaCAgent)
    agent.process_request.return_value = AgentResponse(
        message=response_message,
        status="success",
        pr_url="https://github.com/org/repo/pull/1",
    )
    agent.get_available_resources.return_value = []
    return agent


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


class TestCLIInterfaceInit:
    def test_default_session_id_is_generated(self) -> None:
        cli = CLIInterface()
        assert cli.session_id is not None
        # Should be a valid UUID
        uuid.UUID(cli.session_id)

    def test_custom_session_id_is_preserved(self) -> None:
        sid = "my-session-123"
        cli = CLIInterface(session_id=sid)
        assert cli.session_id == sid

    def test_default_user_id(self) -> None:
        cli = CLIInterface()
        assert cli.user_id == "cli-user"

    def test_custom_user_id(self) -> None:
        cli = CLIInterface(user_id="alice@example.com")
        assert cli.user_id == "alice@example.com"

    def test_agent_stored(self) -> None:
        agent = _make_agent()
        cli = CLIInterface(agent=agent)
        assert cli.agent is agent

    def test_no_agent_by_default(self) -> None:
        cli = CLIInterface()
        assert cli.agent is None

    def test_not_active_initially(self) -> None:
        cli = CLIInterface()
        assert cli._active is False


# ---------------------------------------------------------------------------
# send_message()
# ---------------------------------------------------------------------------


class TestSendMessage:
    def test_returns_agent_response_message(self) -> None:
        agent = _make_agent("Hello from agent")
        cli = CLIInterface(agent=agent, use_rich=False)
        result = cli.send_message("Create an S3 bucket")
        assert result == "Hello from agent"

    def test_calls_process_request_with_message(self) -> None:
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        cli.send_message("I need a Lambda function")
        agent.process_request.assert_called_once()
        call_args = agent.process_request.call_args
        assert call_args[0][0] == "I need a Lambda function"

    def test_passes_conversation_context(self) -> None:
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        cli.send_message("Create a VPC")
        call_args = agent.process_request.call_args
        context = call_args[0][1]
        assert isinstance(context, ConversationContext)
        assert context.session_id == cli.session_id
        assert context.user_id == cli.user_id

    def test_reuses_same_context_across_calls(self) -> None:
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        cli.send_message("First message")
        cli.send_message("Second message")
        # Both calls should use the same context object
        ctx1 = agent.process_request.call_args_list[0][0][1]
        ctx2 = agent.process_request.call_args_list[1][0][1]
        assert ctx1 is ctx2

    def test_raises_runtime_error_without_agent(self) -> None:
        cli = CLIInterface(agent=None, use_rich=False)
        with pytest.raises(RuntimeError, match="No agent configured"):
            cli.send_message("anything")

    def test_raises_type_error_for_wrong_agent_type(self) -> None:
        cli = CLIInterface(agent=object(), use_rich=False)
        with pytest.raises(TypeError, match="BedrockIaCAgent"):
            cli.send_message("anything")


# ---------------------------------------------------------------------------
# display_progress()
# ---------------------------------------------------------------------------


class TestDisplayProgress:
    def test_done_status_plain(self, capsys: pytest.CaptureFixture) -> None:
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Cloning repository", "done")
        captured = capsys.readouterr()
        assert "Cloning repository" in captured.out
        assert "done" in captured.out

    def test_failed_status_plain(self, capsys: pytest.CaptureFixture) -> None:
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Pushing branch", "failed")
        captured = capsys.readouterr()
        # Error output goes to stderr
        assert "Pushing branch" in captured.out or "Pushing branch" in captured.err

    def test_in_progress_status_plain(self, capsys: pytest.CaptureFixture) -> None:
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Creating PR", "in_progress")
        captured = capsys.readouterr()
        assert "Creating PR" in captured.out

    def test_success_status_plain(self, capsys: pytest.CaptureFixture) -> None:
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Authenticating", "success")
        captured = capsys.readouterr()
        assert "Authenticating" in captured.out

    def test_does_not_raise_with_rich_disabled(self) -> None:
        cli = CLIInterface(use_rich=False)
        # Should not raise for any status string
        cli.display_progress("op", "unknown_status")
        cli.display_progress("op", "done")
        cli.display_progress("op", "failed")


# ---------------------------------------------------------------------------
# exit_session()
# ---------------------------------------------------------------------------


class TestExitSession:
    def test_sets_active_false(self) -> None:
        cli = CLIInterface(use_rich=False)
        cli._active = True
        cli.exit_session()
        assert cli._active is False

    def test_prints_goodbye(self, capsys: pytest.CaptureFixture) -> None:
        cli = CLIInterface(use_rich=False)
        cli.exit_session()
        captured = capsys.readouterr()
        assert "Goodbye" in captured.out or "goodbye" in captured.out.lower()


# ---------------------------------------------------------------------------
# start_session() — REPL loop
# ---------------------------------------------------------------------------


class TestStartSession:
    def _run_session(self, inputs: list[str], agent: MagicMock | None = None) -> str:
        """Run start_session() with a sequence of mocked inputs, return stdout."""
        cli = CLIInterface(agent=agent or _make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=inputs):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                cli.start_session()
                return mock_stdout.getvalue()

    def test_exit_command_ends_session(self) -> None:
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=["exit"]):
            cli.start_session()
        assert cli._active is False

    def test_quit_command_ends_session(self) -> None:
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=["quit"]):
            cli.start_session()
        assert cli._active is False

    def test_eof_ends_session_gracefully(self) -> None:
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=EOFError):
            cli.start_session()
        # Should not raise; session ends cleanly

    def test_keyboard_interrupt_ends_session_gracefully(self) -> None:
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            cli.start_session()
        # Should not raise

    def test_message_is_forwarded_to_agent(self) -> None:
        agent = _make_agent("response text")
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["Create an S3 bucket", "exit"]):
            cli.start_session()
        agent.process_request.assert_called_once()
        assert agent.process_request.call_args[0][0] == "Create an S3 bucket"

    def test_empty_input_is_skipped(self) -> None:
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["", "   ", "exit"]):
            cli.start_session()
        # Empty lines should not trigger process_request
        agent.process_request.assert_not_called()

    def test_help_command_does_not_call_agent(self) -> None:
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["help", "exit"]):
            cli.start_session()
        agent.process_request.assert_not_called()

    def test_agent_error_is_handled_gracefully(self) -> None:
        agent = _make_agent()
        agent.process_request.side_effect = RuntimeError("boom")
        cli = CLIInterface(agent=agent, use_rich=False)
        # Should not propagate the exception
        with patch("builtins.input", side_effect=["bad request", "exit"]):
            cli.start_session()  # must not raise

    def test_context_is_maintained_across_turns(self) -> None:
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["first", "second", "exit"]):
            cli.start_session()
        calls = agent.process_request.call_args_list
        assert len(calls) == 2
        # Same context object passed both times
        assert calls[0][0][1] is calls[1][0][1]


# ---------------------------------------------------------------------------
# ProgressIndicator context manager
# ---------------------------------------------------------------------------


class TestProgressIndicator:
    def test_calls_display_progress_on_success(self) -> None:
        cli = MagicMock(spec=CLIInterface)
        with ProgressIndicator("Cloning", cli=cli):
            pass
        cli.display_progress.assert_called_once_with("Cloning", "done")

    def test_calls_display_progress_on_failure(self) -> None:
        cli = MagicMock(spec=CLIInterface)
        with pytest.raises(ValueError):
            with ProgressIndicator("Pushing", cli=cli):
                raise ValueError("network error")
        cli.display_progress.assert_called_once_with("Pushing", "failed")

    def test_works_without_cli(self) -> None:
        # Should not raise even without a CLIInterface
        with ProgressIndicator("op"):
            pass


# ---------------------------------------------------------------------------
# Click command structure — entry point and subcommands
# ---------------------------------------------------------------------------


class TestClickCommands:
    """Tests for the Click CLI entry point and command structure.

    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
    """

    def test_main_help_exits_zero(self) -> None:
        """main --help should print usage and exit 0."""
        from click.testing import CliRunner

        from bedrock_iac_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "bedrock" in result.output.lower() or "iac" in result.output.lower()

    def test_chat_subcommand_exists(self) -> None:
        """'chat' subcommand should be registered on main."""
        from click.testing import CliRunner

        from bedrock_iac_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert result.exit_code == 0
        assert "chat" in result.output.lower() or "session" in result.output.lower()

    def test_list_resources_subcommand_exists(self) -> None:
        """'list-resources' subcommand should be registered on main."""
        from click.testing import CliRunner

        from bedrock_iac_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["list-resources", "--help"])
        assert result.exit_code == 0

    def test_chat_accepts_user_id_option(self) -> None:
        """'chat' should accept --user-id option."""
        from click.testing import CliRunner

        from bedrock_iac_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert "--user-id" in result.output

    def test_chat_accepts_session_id_option(self) -> None:
        """'chat' should accept --session-id option."""
        from click.testing import CliRunner

        from bedrock_iac_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert "--session-id" in result.output

    def test_chat_accepts_github_token_option(self) -> None:
        """'chat' should accept --github-token option."""
        from click.testing import CliRunner

        from bedrock_iac_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert "--github-token" in result.output

    def test_chat_accepts_github_org_option(self) -> None:
        """'chat' should accept --github-org option."""
        from click.testing import CliRunner

        from bedrock_iac_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert "--github-org" in result.output

    def test_chat_accepts_github_repo_option(self) -> None:
        """'chat' should accept --github-repo option."""
        from click.testing import CliRunner

        from bedrock_iac_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert "--github-repo" in result.output

    def test_chat_accepts_bedrock_model_id_option(self) -> None:
        """'chat' should accept --bedrock-model-id option."""
        from click.testing import CliRunner

        from bedrock_iac_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert "--bedrock-model-id" in result.output

    def test_chat_accepts_aws_region_option(self) -> None:
        """'chat' should accept --aws-region option."""
        from click.testing import CliRunner

        from bedrock_iac_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert "--aws-region" in result.output

    def test_list_resources_without_agent_exits_nonzero(self) -> None:
        """list-resources should exit non-zero when agent cannot be built."""
        from click.testing import CliRunner

        from bedrock_iac_agent.cli import main

        runner = CliRunner()
        # Patch _build_agent_or_none to return None
        with patch("bedrock_iac_agent.cli._build_agent_or_none", return_value=None):
            result = runner.invoke(main, ["list-resources"])
        assert result.exit_code != 0

    def test_list_resources_with_agent_exits_zero(self) -> None:
        """list-resources should exit 0 when agent is available."""
        from click.testing import CliRunner

        from bedrock_iac_agent.cli import main
        from bedrock_iac_agent.models import ResourceType

        agent = _make_agent()
        agent.get_available_resources.return_value = [ResourceType.S3_BUCKET]

        runner = CliRunner()
        with patch("bedrock_iac_agent.cli._build_agent_or_none", return_value=agent):
            result = runner.invoke(main, ["list-resources"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# _build_agent_or_none() configuration loading
# ---------------------------------------------------------------------------


class TestBuildAgentOrNone:
    """Tests for the agent factory helper and configuration loading.

    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5

    Note: _build_agent_or_none uses lazy relative imports inside the function
    body, so we patch the actual module-level classes rather than cli-level names.
    """

    # Patch targets — the actual module paths where each class is defined.
    _NLP = "bedrock_iac_agent.natural_language_parser.NaturalLanguageParser"
    _CFG = "bedrock_iac_agent.configuration_generator.ConfigurationGenerator"
    _INV = "bedrock_iac_agent.golden_modules_inventory.GoldenModulesInventory"
    _AUD = "bedrock_iac_agent.audit_logger.AuditLogger"
    _AGT = "bedrock_iac_agent.agent.BedrockIaCAgent"
    _GHI = "bedrock_iac_agent.github_integration.GitHubIntegration"
    _GHC = "bedrock_iac_agent.models.GitHubCredentials"

    def test_returns_none_on_exception(self) -> None:
        """Should return None gracefully when agent construction raises."""
        from bedrock_iac_agent.cli import _build_agent_or_none

        with patch(self._NLP, side_effect=RuntimeError("import failed")):
            result = _build_agent_or_none()
        assert result is None

    def test_github_integration_wired_when_full_credentials_provided(self) -> None:
        """Agent should include GitHubIntegration when token, org, and repo are all set."""
        from bedrock_iac_agent.cli import _build_agent_or_none

        mock_github_instance = MagicMock()
        captured: dict = {}

        def fake_agent(**kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return MagicMock()

        with (
            patch(self._NLP),
            patch(self._CFG),
            patch(self._INV),
            patch(self._AUD),
            patch(self._GHI, return_value=mock_github_instance),
            patch(self._AGT, side_effect=fake_agent),
        ):
            _build_agent_or_none(
                github_token="ghp_test",
                github_org="my-org",
                github_repo="my-repo",
            )

        assert captured.get("github_integration") is mock_github_instance

    def test_github_integration_none_when_credentials_missing(self) -> None:
        """Agent should have github_integration=None when no credentials are provided."""
        import os

        from bedrock_iac_agent.cli import _build_agent_or_none

        captured: dict = {}

        def fake_agent(**kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return MagicMock()

        # Remove any GitHub env vars that might be set in the test environment
        clean_env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "GITHUB_ORG", "GITHUB_REPO")}

        with (
            patch(self._NLP),
            patch(self._CFG),
            patch(self._INV),
            patch(self._AUD),
            patch(self._AGT, side_effect=fake_agent),
            patch.dict("os.environ", clean_env, clear=True),
        ):
            _build_agent_or_none()

        assert captured.get("github_integration") is None

    def test_env_vars_used_as_fallback_for_github_credentials(self) -> None:
        """GITHUB_TOKEN, GITHUB_ORG, GITHUB_REPO env vars should be used when args not provided."""
        from bedrock_iac_agent.cli import _build_agent_or_none

        credentials_calls: list = []

        def fake_credentials(**kwargs):  # type: ignore[no-untyped-def]
            credentials_calls.append(kwargs)
            return MagicMock()

        env = {
            "GITHUB_TOKEN": "env-token",
            "GITHUB_ORG": "env-org",
            "GITHUB_REPO": "env-repo",
        }

        with (
            patch(self._NLP),
            patch(self._CFG),
            patch(self._INV),
            patch(self._AUD),
            patch(self._GHI),
            patch(self._GHC, side_effect=fake_credentials),
            patch(self._AGT),
            patch.dict("os.environ", env),
        ):
            _build_agent_or_none()

        assert len(credentials_calls) == 1
        assert credentials_calls[0]["token"] == "env-token"
        assert credentials_calls[0]["organization"] == "env-org"
        assert credentials_calls[0]["repository"] == "env-repo"

    def test_repo_url_passed_to_agent(self) -> None:
        """repo_url should be forwarded to BedrockIaCAgent."""
        from bedrock_iac_agent.cli import _build_agent_or_none

        captured: dict = {}

        def fake_agent(**kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return MagicMock()

        with (
            patch(self._NLP),
            patch(self._CFG),
            patch(self._INV),
            patch(self._AUD),
            patch(self._AGT, side_effect=fake_agent),
        ):
            _build_agent_or_none(github_repo_url="https://github.com/org/repo")

        assert captured.get("repo_url") == "https://github.com/org/repo"

    def test_bedrock_model_id_passed_to_nlp_parser(self) -> None:
        """bedrock_model_id should be forwarded to NaturalLanguageParser."""
        from bedrock_iac_agent.cli import _build_agent_or_none

        nlp_calls: list = []

        def fake_nlp(**kwargs):  # type: ignore[no-untyped-def]
            nlp_calls.append(kwargs)
            return MagicMock()

        with (
            patch(self._NLP, side_effect=fake_nlp),
            patch(self._CFG),
            patch(self._INV),
            patch(self._AUD),
            patch(self._AGT),
        ):
            _build_agent_or_none(bedrock_model_id="anthropic.claude-3-sonnet-20240229-v1:0")

        assert len(nlp_calls) == 1
        assert nlp_calls[0]["model_id"] == "anthropic.claude-3-sonnet-20240229-v1:0"

    def test_aws_region_passed_to_nlp_parser(self) -> None:
        """aws_region should be forwarded to NaturalLanguageParser."""
        from bedrock_iac_agent.cli import _build_agent_or_none

        nlp_calls: list = []

        def fake_nlp(**kwargs):  # type: ignore[no-untyped-def]
            nlp_calls.append(kwargs)
            return MagicMock()

        with (
            patch(self._NLP, side_effect=fake_nlp),
            patch(self._CFG),
            patch(self._INV),
            patch(self._AUD),
            patch(self._AGT),
        ):
            _build_agent_or_none(aws_region="eu-west-1")

        assert len(nlp_calls) == 1
        assert nlp_calls[0]["region_name"] == "eu-west-1"
