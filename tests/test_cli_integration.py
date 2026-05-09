"""Integration tests for the CLI interface.

Tests cover end-to-end flows using Click CliRunner and mocked agent responses.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

from __future__ import annotations

import uuid
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from bedrock_iac_agent.cli import CLIInterface, ProgressIndicator, main
from bedrock_iac_agent.models import AgentResponse, ConversationContext, ResourceType


# ---------------------------------------------------------------------------
# Helpers
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
    agent.get_available_resources.return_value = [
        ResourceType.S3_BUCKET,
        ResourceType.LAMBDA_FUNCTION,
    ]
    return agent


# ---------------------------------------------------------------------------
# Requirement 10.1: CLI accepts text commands from user
# ---------------------------------------------------------------------------


class TestCLIAcceptsTextCommands:
    """Requirement 10.1: CLI_Interface SHALL accept text commands from user."""

    def test_chat_subcommand_invokes_session(self) -> None:
        """Invoking 'chat' subcommand starts an interactive session."""
        runner = CliRunner()
        agent = _make_agent()
        with patch("bedrock_iac_agent.cli._build_agent_or_none", return_value=agent):
            with patch("builtins.input", side_effect=["exit"]):
                result = runner.invoke(main, ["chat"])
        assert result.exit_code == 0

    def test_user_message_forwarded_to_agent(self) -> None:
        """User text input is forwarded to the agent's process_request."""
        agent = _make_agent("Configuration generated")
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["Create an S3 bucket for logs", "exit"]):
            cli.start_session()
        agent.process_request.assert_called_once()
        assert agent.process_request.call_args[0][0] == "Create an S3 bucket for logs"

    def test_multiple_commands_in_session(self) -> None:
        """Multiple user messages are each forwarded to the agent."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["Create S3 bucket", "Create Lambda function", "exit"]):
            cli.start_session()
        assert agent.process_request.call_count == 2

    def test_whitespace_only_input_ignored(self) -> None:
        """Whitespace-only input lines are skipped without calling the agent."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["   ", "\t", "exit"]):
            cli.start_session()
        agent.process_request.assert_not_called()

    def test_send_message_returns_string(self) -> None:
        """send_message() returns the agent's response as a plain string."""
        agent = _make_agent("Hello from agent")
        cli = CLIInterface(agent=agent, use_rich=False)
        result = cli.send_message("Create a VPC")
        assert isinstance(result, str)
        assert result == "Hello from agent"

    def test_send_message_passes_message_to_agent(self) -> None:
        """send_message() passes the exact message string to process_request."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        cli.send_message("I need a Lambda function for staging")
        call_args = agent.process_request.call_args
        assert call_args[0][0] == "I need a Lambda function for staging"


# ---------------------------------------------------------------------------
# Requirement 10.2: CLI displays agent responses in readable format
# ---------------------------------------------------------------------------


class TestCLIDisplaysResponses:
    """Requirement 10.2: CLI_Interface SHALL display agent responses in readable format."""

    def test_agent_response_printed_to_stdout(self, capsys: pytest.CaptureFixture) -> None:
        """Agent response text appears in stdout."""
        agent = _make_agent("Your S3 bucket is ready")
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["Create S3 bucket", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "Your S3 bucket is ready" in captured.out

    def test_agent_response_prefixed_with_agent_label(self, capsys: pytest.CaptureFixture) -> None:
        """Agent responses are prefixed with 'Agent>' label."""
        agent = _make_agent("Done!")
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["Create S3 bucket", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "Agent>" in captured.out

    def test_welcome_banner_displayed_on_start(self, capsys: pytest.CaptureFixture) -> None:
        """Welcome banner is shown when session starts."""
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=["exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "Bedrock IaC Agent" in captured.out

    def test_help_command_shows_available_commands(self, capsys: pytest.CaptureFixture) -> None:
        """'help' command prints available commands."""
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=["help", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "exit" in captured.out.lower() or "quit" in captured.out.lower()

    def test_question_mark_shows_help(self, capsys: pytest.CaptureFixture) -> None:
        """'?' is an alias for 'help'."""
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=["?", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "help" in captured.out.lower() or "exit" in captured.out.lower()

    def test_list_resources_command_shows_resources(self, capsys: pytest.CaptureFixture) -> None:
        """'resources' command lists available resource types."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["resources", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "s3_bucket" in captured.out or "lambda_function" in captured.out

    def test_list_command_alias_works(self, capsys: pytest.CaptureFixture) -> None:
        """'list' is an alias for 'resources'."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["list", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "s3_bucket" in captured.out or "lambda_function" in captured.out

    def test_error_response_displayed(self, capsys: pytest.CaptureFixture) -> None:
        """Errors from the agent are displayed to the user."""
        agent = _make_agent()
        agent.process_request.side_effect = RuntimeError("Something went wrong")
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["bad request", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "Error" in captured.out or "error" in captured.err or "Something went wrong" in captured.err

    def test_print_agent_response_method(self, capsys: pytest.CaptureFixture) -> None:
        """_print_agent_response outputs the response with Agent> prefix."""
        cli = CLIInterface(use_rich=False)
        cli._print_agent_response("Test response text")
        captured = capsys.readouterr()
        assert "Agent>" in captured.out
        assert "Test response text" in captured.out

    def test_print_error_method(self, capsys: pytest.CaptureFixture) -> None:
        """_print_error outputs error messages."""
        cli = CLIInterface(use_rich=False)
        cli._print_error("Something failed badly")
        captured = capsys.readouterr()
        assert "Something failed badly" in captured.out or "Something failed badly" in captured.err


# ---------------------------------------------------------------------------
# Requirement 10.3: CLI supports conversational sessions with maintained context
# ---------------------------------------------------------------------------


class TestCLIConversationalContext:
    """Requirement 10.3: CLI_Interface SHALL support conversational sessions with maintained context."""

    def test_same_context_used_across_turns(self) -> None:
        """The same ConversationContext object is passed for every message in a session."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["first message", "second message", "exit"]):
            cli.start_session()
        calls = agent.process_request.call_args_list
        assert len(calls) == 2
        ctx1 = calls[0][0][1]
        ctx2 = calls[1][0][1]
        assert ctx1 is ctx2

    def test_context_has_correct_session_id(self) -> None:
        """ConversationContext carries the session_id provided at construction."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False, session_id="test-session-123")
        with patch("builtins.input", side_effect=["hello", "exit"]):
            cli.start_session()
        ctx = agent.process_request.call_args[0][1]
        assert ctx.session_id == "test-session-123"

    def test_context_has_correct_user_id(self) -> None:
        """ConversationContext carries the user_id provided at construction."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False, user_id="alice@example.com")
        with patch("builtins.input", side_effect=["hello", "exit"]):
            cli.start_session()
        ctx = agent.process_request.call_args[0][1]
        assert ctx.user_id == "alice@example.com"

    def test_context_is_conversation_context_instance(self) -> None:
        """The context passed to the agent is a ConversationContext instance."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["hello", "exit"]):
            cli.start_session()
        ctx = agent.process_request.call_args[0][1]
        assert isinstance(ctx, ConversationContext)

    def test_send_message_reuses_context_across_calls(self) -> None:
        """send_message() reuses the same context object across multiple calls."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        cli.send_message("first")
        cli.send_message("second")
        ctx1 = agent.process_request.call_args_list[0][0][1]
        ctx2 = agent.process_request.call_args_list[1][0][1]
        assert ctx1 is ctx2

    def test_session_id_auto_generated_when_not_provided(self) -> None:
        """A UUID session_id is auto-generated when none is provided."""
        cli = CLIInterface(use_rich=False)
        assert cli.session_id is not None
        uuid.UUID(cli.session_id)  # validates it is a proper UUID

    def test_context_created_lazily_on_first_send(self) -> None:
        """Context is created on first send_message call, not at construction."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        assert cli._context is None
        cli.send_message("hello")
        assert cli._context is not None

    def test_three_turn_conversation_uses_same_context(self) -> None:
        """Three consecutive messages all use the same context object."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["msg1", "msg2", "msg3", "exit"]):
            cli.start_session()
        calls = agent.process_request.call_args_list
        assert len(calls) == 3
        ctx0 = calls[0][0][1]
        ctx1 = calls[1][0][1]
        ctx2 = calls[2][0][1]
        assert ctx0 is ctx1 is ctx2


# ---------------------------------------------------------------------------
# Requirement 10.4: CLI allows clean session exit
# ---------------------------------------------------------------------------


class TestCLICleanExit:
    """Requirement 10.4: CLI_Interface SHALL allow clean session exit."""

    def test_exit_command_ends_session(self) -> None:
        """'exit' command terminates the REPL loop."""
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=["exit"]):
            cli.start_session()
        assert cli._active is False

    def test_quit_command_ends_session(self) -> None:
        """'quit' command terminates the REPL loop."""
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=["quit"]):
            cli.start_session()
        assert cli._active is False

    def test_bye_command_ends_session(self) -> None:
        """'bye' command terminates the REPL loop."""
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=["bye"]):
            cli.start_session()
        assert cli._active is False

    def test_q_command_ends_session(self) -> None:
        """'q' command terminates the REPL loop."""
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=["q"]):
            cli.start_session()
        assert cli._active is False

    def test_colon_q_command_ends_session(self) -> None:
        """':q' (vim-style) command terminates the REPL loop."""
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=[":q"]):
            cli.start_session()
        assert cli._active is False

    def test_eof_ends_session_gracefully(self) -> None:
        """EOF (Ctrl-D) ends the session without raising an exception."""
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=EOFError):
            cli.start_session()  # must not raise

    def test_keyboard_interrupt_ends_session_gracefully(self) -> None:
        """Ctrl-C ends the session without raising an exception."""
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            cli.start_session()  # must not raise

    def test_exit_session_method_sets_active_false(self) -> None:
        """exit_session() sets _active to False."""
        cli = CLIInterface(use_rich=False)
        cli._active = True
        cli.exit_session()
        assert cli._active is False

    def test_exit_session_prints_goodbye(self, capsys: pytest.CaptureFixture) -> None:
        """exit_session() prints a goodbye message."""
        cli = CLIInterface(use_rich=False)
        cli.exit_session()
        captured = capsys.readouterr()
        assert "goodbye" in captured.out.lower() or "session ended" in captured.out.lower()

    def test_exit_command_case_insensitive(self) -> None:
        """Exit commands are matched case-insensitively."""
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=["EXIT"]):
            cli.start_session()
        assert cli._active is False

    def test_exit_does_not_call_agent(self) -> None:
        """Exit commands do not trigger a call to the agent."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["exit"]):
            cli.start_session()
        agent.process_request.assert_not_called()

    def test_eof_prints_interrupted_message(self, capsys: pytest.CaptureFixture) -> None:
        """EOF prints a session interrupted message."""
        cli = CLIInterface(agent=_make_agent(), use_rich=False)
        with patch("builtins.input", side_effect=EOFError):
            cli.start_session()
        captured = capsys.readouterr()
        assert "interrupted" in captured.out.lower() or "goodbye" in captured.out.lower()


# ---------------------------------------------------------------------------
# Requirement 10.5: CLI shows progress indicators during long operations
# ---------------------------------------------------------------------------


class TestCLIProgressIndicators:
    """Requirement 10.5: CLI_Interface SHALL show progress indicators during long operations."""

    def test_display_progress_done_shows_output(self, capsys: pytest.CaptureFixture) -> None:
        """display_progress with 'done' status shows operation name and status."""
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Cloning repository", "done")
        captured = capsys.readouterr()
        assert "Cloning repository" in captured.out
        assert "done" in captured.out

    def test_display_progress_success_shows_output(self, capsys: pytest.CaptureFixture) -> None:
        """display_progress with 'success' status shows operation name and status."""
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Pushing branch", "success")
        captured = capsys.readouterr()
        assert "Pushing branch" in captured.out
        assert "success" in captured.out

    def test_display_progress_failed_shows_output(self, capsys: pytest.CaptureFixture) -> None:
        """display_progress with 'failed' status shows operation name."""
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Creating PR", "failed")
        captured = capsys.readouterr()
        assert "Creating PR" in captured.out or "Creating PR" in captured.err

    def test_display_progress_in_progress_shows_output(self, capsys: pytest.CaptureFixture) -> None:
        """display_progress with 'in_progress' status shows operation name."""
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Cloning repository", "in_progress")
        captured = capsys.readouterr()
        assert "Cloning repository" in captured.out

    def test_display_progress_complete_status(self, capsys: pytest.CaptureFixture) -> None:
        """display_progress with 'complete' status shows operation name."""
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Authenticating", "complete")
        captured = capsys.readouterr()
        assert "Authenticating" in captured.out

    def test_display_progress_completed_status(self, capsys: pytest.CaptureFixture) -> None:
        """display_progress with 'completed' status shows operation name."""
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Authenticating", "completed")
        captured = capsys.readouterr()
        assert "Authenticating" in captured.out

    def test_display_progress_error_status(self, capsys: pytest.CaptureFixture) -> None:
        """display_progress with 'error' status shows operation name."""
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Pushing branch", "error")
        captured = capsys.readouterr()
        assert "Pushing branch" in captured.out or "Pushing branch" in captured.err

    def test_progress_indicator_context_manager_success(self) -> None:
        """ProgressIndicator calls display_progress with 'done' on clean exit."""
        cli = MagicMock(spec=CLIInterface)
        with ProgressIndicator("Cloning repository", cli=cli):
            pass
        cli.display_progress.assert_called_once_with("Cloning repository", "done")

    def test_progress_indicator_context_manager_failure(self) -> None:
        """ProgressIndicator calls display_progress with 'failed' on exception."""
        cli = MagicMock(spec=CLIInterface)
        with pytest.raises(RuntimeError):
            with ProgressIndicator("Pushing branch", cli=cli):
                raise RuntimeError("network error")
        cli.display_progress.assert_called_once_with("Pushing branch", "failed")

    def test_progress_indicator_without_cli_does_not_raise(self, capsys: pytest.CaptureFixture) -> None:
        """ProgressIndicator works without a CLIInterface (plain output)."""
        with ProgressIndicator("Cloning repository"):
            pass
        captured = capsys.readouterr()
        assert "Cloning repository" in captured.out

    def test_progress_indicator_failure_without_cli(self, capsys: pytest.CaptureFixture) -> None:
        """ProgressIndicator shows failure output even without a CLIInterface."""
        with pytest.raises(ValueError):
            with ProgressIndicator("Pushing branch"):
                raise ValueError("push failed")
        captured = capsys.readouterr()
        assert "Pushing branch" in captured.out

    def test_display_progress_cloning_operation(self, capsys: pytest.CaptureFixture) -> None:
        """Progress indicator works for cloning operation (Req 10.5)."""
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Cloning repository", "in_progress")
        captured = capsys.readouterr()
        assert "Cloning repository" in captured.out

    def test_display_progress_push_operation(self, capsys: pytest.CaptureFixture) -> None:
        """Progress indicator works for push operation (Req 10.5)."""
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Pushing branch", "done")
        captured = capsys.readouterr()
        assert "Pushing branch" in captured.out

    def test_display_progress_pr_creation_operation(self, capsys: pytest.CaptureFixture) -> None:
        """Progress indicator works for PR creation operation (Req 10.5)."""
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Creating PR", "done")
        captured = capsys.readouterr()
        assert "Creating PR" in captured.out

    def test_display_progress_does_not_raise_for_unknown_status(self) -> None:
        """display_progress handles unknown status strings without raising."""
        cli = CLIInterface(use_rich=False)
        cli.display_progress("Some operation", "unknown_status_xyz")


# ---------------------------------------------------------------------------
# Integration: Click command parsing
# ---------------------------------------------------------------------------


class TestClickCommandParsing:
    """Integration tests for Click command parsing and option handling."""

    def test_main_help_exits_zero(self) -> None:
        """main --help exits with code 0."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_main_help_mentions_bedrock_or_iac(self) -> None:
        """main --help output mentions the agent name."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "bedrock" in result.output.lower() or "iac" in result.output.lower()

    def test_chat_help_shows_all_options(self) -> None:
        """'chat --help' lists all expected options."""
        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert result.exit_code == 0
        assert "--user-id" in result.output
        assert "--session-id" in result.output
        assert "--github-token" in result.output
        assert "--github-org" in result.output
        assert "--github-repo" in result.output
        assert "--bedrock-model-id" in result.output
        assert "--aws-region" in result.output

    def test_list_resources_help_exits_zero(self) -> None:
        """'list-resources --help' exits with code 0."""
        runner = CliRunner()
        result = runner.invoke(main, ["list-resources", "--help"])
        assert result.exit_code == 0

    def test_chat_with_user_id_option(self) -> None:
        """'chat --user-id' option is accepted."""
        runner = CliRunner()
        agent = _make_agent()
        with patch("bedrock_iac_agent.cli._build_agent_or_none", return_value=agent):
            with patch("builtins.input", side_effect=["exit"]):
                result = runner.invoke(main, ["chat", "--user-id", "bob@example.com"])
        assert result.exit_code == 0

    def test_chat_with_session_id_option(self) -> None:
        """'chat --session-id' option is accepted."""
        runner = CliRunner()
        agent = _make_agent()
        with patch("bedrock_iac_agent.cli._build_agent_or_none", return_value=agent):
            with patch("builtins.input", side_effect=["exit"]):
                result = runner.invoke(main, ["chat", "--session-id", "my-session-abc"])
        assert result.exit_code == 0

    def test_chat_with_bedrock_model_id_option(self) -> None:
        """'chat --bedrock-model-id' option is accepted."""
        runner = CliRunner()
        agent = _make_agent()
        with patch("bedrock_iac_agent.cli._build_agent_or_none", return_value=agent):
            with patch("builtins.input", side_effect=["exit"]):
                result = runner.invoke(
                    main,
                    ["chat", "--bedrock-model-id", "anthropic.claude-3-sonnet-20240229-v1:0"],
                )
        assert result.exit_code == 0

    def test_chat_with_aws_region_option(self) -> None:
        """'chat --aws-region' option is accepted."""
        runner = CliRunner()
        agent = _make_agent()
        with patch("bedrock_iac_agent.cli._build_agent_or_none", return_value=agent):
            with patch("builtins.input", side_effect=["exit"]):
                result = runner.invoke(main, ["chat", "--aws-region", "eu-west-1"])
        assert result.exit_code == 0

    def test_chat_reads_github_token_from_env(self) -> None:
        """GITHUB_TOKEN env var is passed to _build_agent_or_none."""
        runner = CliRunner()
        captured_kwargs: dict = {}

        def fake_build(**kwargs):  # type: ignore[no-untyped-def]
            captured_kwargs.update(kwargs)
            return _make_agent()

        with patch("bedrock_iac_agent.cli._build_agent_or_none", side_effect=fake_build):
            with patch("builtins.input", side_effect=["exit"]):
                result = runner.invoke(
                    main,
                    ["chat"],
                    env={"GITHUB_TOKEN": "env-token-123"},
                )
        assert result.exit_code == 0
        assert captured_kwargs.get("github_token") == "env-token-123"

    def test_chat_reads_github_org_from_env(self) -> None:
        """GITHUB_ORG env var is passed to _build_agent_or_none."""
        runner = CliRunner()
        captured_kwargs: dict = {}

        def fake_build(**kwargs):  # type: ignore[no-untyped-def]
            captured_kwargs.update(kwargs)
            return _make_agent()

        with patch("bedrock_iac_agent.cli._build_agent_or_none", side_effect=fake_build):
            with patch("builtins.input", side_effect=["exit"]):
                result = runner.invoke(
                    main,
                    ["chat"],
                    env={"GITHUB_ORG": "my-org"},
                )
        assert result.exit_code == 0
        assert captured_kwargs.get("github_org") == "my-org"

    def test_chat_reads_github_repo_from_env(self) -> None:
        """GITHUB_REPO env var is passed to _build_agent_or_none."""
        runner = CliRunner()
        captured_kwargs: dict = {}

        def fake_build(**kwargs):  # type: ignore[no-untyped-def]
            captured_kwargs.update(kwargs)
            return _make_agent()

        with patch("bedrock_iac_agent.cli._build_agent_or_none", side_effect=fake_build):
            with patch("builtins.input", side_effect=["exit"]):
                result = runner.invoke(
                    main,
                    ["chat"],
                    env={"GITHUB_REPO": "my-repo"},
                )
        assert result.exit_code == 0
        assert captured_kwargs.get("github_repo") == "my-repo"

    def test_list_resources_without_agent_exits_nonzero(self) -> None:
        """list-resources exits non-zero when agent cannot be built."""
        runner = CliRunner()
        with patch("bedrock_iac_agent.cli._build_agent_or_none", return_value=None):
            result = runner.invoke(main, ["list-resources"])
        assert result.exit_code != 0

    def test_list_resources_with_agent_exits_zero(self) -> None:
        """list-resources exits 0 when agent is available."""
        runner = CliRunner()
        agent = _make_agent()
        with patch("bedrock_iac_agent.cli._build_agent_or_none", return_value=agent):
            result = runner.invoke(main, ["list-resources"])
        assert result.exit_code == 0

    def test_list_resources_output_contains_resource_types(self) -> None:
        """list-resources output includes resource type names."""
        runner = CliRunner()
        agent = _make_agent()
        with patch("bedrock_iac_agent.cli._build_agent_or_none", return_value=agent):
            result = runner.invoke(main, ["list-resources"])
        assert "s3_bucket" in result.output or "lambda_function" in result.output

    def test_default_invocation_starts_chat(self) -> None:
        """Invoking main with no subcommand starts the chat session."""
        runner = CliRunner()
        agent = _make_agent()
        with patch("bedrock_iac_agent.cli._build_agent_or_none", return_value=agent):
            with patch("builtins.input", side_effect=["exit"]):
                result = runner.invoke(main, [])
        assert result.exit_code == 0

    def test_chat_github_repo_url_option(self) -> None:
        """'chat --github-repo-url' option is accepted."""
        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert "--github-repo-url" in result.output


# ---------------------------------------------------------------------------
# Integration: Error display
# ---------------------------------------------------------------------------


class TestCLIErrorDisplay:
    """Integration tests for error display in the CLI."""

    def test_agent_exception_displayed_as_error(self, capsys: pytest.CaptureFixture) -> None:
        """Exceptions from the agent are caught and displayed as errors."""
        agent = _make_agent()
        agent.process_request.side_effect = RuntimeError("Bedrock API unavailable")
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["Create S3 bucket", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "Error" in captured.out or "Error" in captured.err or "ERROR" in captured.err

    def test_no_agent_error_displayed_gracefully(self, capsys: pytest.CaptureFixture) -> None:
        """When no agent is configured, error is shown gracefully."""
        cli = CLIInterface(agent=None, use_rich=False)
        with patch("builtins.input", side_effect=["Create S3 bucket", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "Error" in captured.out or "Error" in captured.err or "ERROR" in captured.err

    def test_list_resources_without_agent_shows_message(self, capsys: pytest.CaptureFixture) -> None:
        """_list_resources() shows a message when no agent is configured."""
        cli = CLIInterface(agent=None, use_rich=False)
        cli._list_resources()
        captured = capsys.readouterr()
        assert "no agent" in captured.out.lower() or "not configured" in captured.out.lower()

    def test_send_message_without_agent_raises_runtime_error(self) -> None:
        """send_message() raises RuntimeError when no agent is configured."""
        cli = CLIInterface(agent=None, use_rich=False)
        with pytest.raises(RuntimeError, match="No agent configured"):
            cli.send_message("anything")

    def test_send_message_with_wrong_agent_type_raises_type_error(self) -> None:
        """send_message() raises TypeError when agent is not a BedrockIaCAgent."""
        cli = CLIInterface(agent=object(), use_rich=False)
        with pytest.raises(TypeError, match="BedrockIaCAgent"):
            cli.send_message("anything")

    def test_session_continues_after_agent_error(self) -> None:
        """Session continues processing after an agent error on one turn."""
        agent = _make_agent()
        agent.process_request.side_effect = [
            RuntimeError("first call fails"),
            AgentResponse(message="second call succeeds", status="success"),
        ]
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["first", "second", "exit"]):
            cli.start_session()
        assert agent.process_request.call_count == 2

    def test_error_message_contains_exception_text(self, capsys: pytest.CaptureFixture) -> None:
        """Error display includes the exception message text."""
        agent = _make_agent()
        agent.process_request.side_effect = RuntimeError("specific error message here")
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["bad request", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "specific error message here" in captured.out or "specific error message here" in captured.err


# ---------------------------------------------------------------------------
# Integration: Full session flow
# ---------------------------------------------------------------------------


class TestFullSessionFlow:
    """End-to-end integration tests for complete CLI session flows."""

    def test_complete_session_flow(self, capsys: pytest.CaptureFixture) -> None:
        """Full session: banner → request → response → exit."""
        agent = _make_agent("PR created: https://github.com/org/repo/pull/42")
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["Create an S3 bucket for logs", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "Bedrock IaC Agent" in captured.out
        assert "PR created" in captured.out
        assert "goodbye" in captured.out.lower() or "session ended" in captured.out.lower()

    def test_session_with_help_then_request_then_exit(self, capsys: pytest.CaptureFixture) -> None:
        """Session: help → request → exit."""
        agent = _make_agent("Lambda function created")
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["help", "Create Lambda function", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "Lambda function created" in captured.out
        agent.process_request.assert_called_once()

    def test_session_with_resources_then_request_then_exit(self, capsys: pytest.CaptureFixture) -> None:
        """Session: resources → request → exit."""
        agent = _make_agent("VPC created")
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["resources", "Create a VPC", "exit"]):
            cli.start_session()
        captured = capsys.readouterr()
        assert "VPC created" in captured.out
        agent.process_request.assert_called_once()

    def test_session_with_empty_lines_then_request(self) -> None:
        """Empty lines are skipped; only real requests reach the agent."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False)
        with patch("builtins.input", side_effect=["", "  ", "Create S3 bucket", "exit"]):
            cli.start_session()
        agent.process_request.assert_called_once()
        assert agent.process_request.call_args[0][0] == "Create S3 bucket"

    def test_session_via_click_runner_with_mocked_agent(self) -> None:
        """Full session via CliRunner with mocked agent exits cleanly."""
        runner = CliRunner()
        agent = _make_agent("Configuration generated successfully")
        with patch("bedrock_iac_agent.cli._build_agent_or_none", return_value=agent):
            with patch("builtins.input", side_effect=["Create an RDS database", "exit"]):
                result = runner.invoke(main, ["chat", "--user-id", "dev@example.com"])
        assert result.exit_code == 0

    def test_session_user_id_propagated_to_context(self) -> None:
        """user_id from --user-id option is propagated to the conversation context."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False, user_id="dev@example.com")
        with patch("builtins.input", side_effect=["Create S3 bucket", "exit"]):
            cli.start_session()
        ctx = agent.process_request.call_args[0][1]
        assert ctx.user_id == "dev@example.com"

    def test_session_session_id_propagated_to_context(self) -> None:
        """session_id from --session-id option is propagated to the conversation context."""
        agent = _make_agent()
        cli = CLIInterface(agent=agent, use_rich=False, session_id="fixed-session-id")
        with patch("builtins.input", side_effect=["Create S3 bucket", "exit"]):
            cli.start_session()
        ctx = agent.process_request.call_args[0][1]
        assert ctx.session_id == "fixed-session-id"
