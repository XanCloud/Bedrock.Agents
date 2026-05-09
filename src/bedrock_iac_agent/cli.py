"""CLI Interface for the Bedrock IaC Agent.

Provides an interactive REPL-style command-line interface for interacting
with the BedrockIaCAgent. Uses Click for command structure and Rich for
colored output and progress indicators.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

from __future__ import annotations

import logging
import sys
import uuid
from typing import Optional

import click

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Rich support — gracefully degrade to plain output if not installed
# ---------------------------------------------------------------------------

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.text import Text
    from rich.theme import Theme

    _RICH_AVAILABLE = True

    _THEME = Theme(
        {
            "user": "bold cyan",
            "agent": "bold green",
            "error": "bold red",
            "warning": "bold yellow",
            "info": "dim white",
            "progress": "bold blue",
            "banner": "bold magenta",
        }
    )
    _console = Console(theme=_THEME)
    _err_console = Console(stderr=True, theme=_THEME)

except ImportError:  # pragma: no cover
    _RICH_AVAILABLE = False
    _console = None  # type: ignore[assignment]
    _err_console = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# CLIInterface
# ---------------------------------------------------------------------------


class CLIInterface:
    """Interactive CLI for the Bedrock IaC Agent.

    Provides a REPL-style interface that reads user input, forwards messages
    to a :class:`~bedrock_iac_agent.agent.BedrockIaCAgent`, and displays
    responses with colored formatting and progress indicators.

    Args:
        agent: A configured :class:`~bedrock_iac_agent.agent.BedrockIaCAgent`
            instance.  When ``None``, the CLI can still be instantiated but
            :meth:`send_message` will raise a ``RuntimeError``.
        user_id: Identifier for the current user (used in conversation context).
        session_id: Optional session identifier.  A UUID is generated when
            ``None``.
        use_rich: Whether to use Rich for colored output.  Defaults to
            ``True`` when Rich is installed.

    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
    """

    # Prompt shown to the user on each REPL iteration
    PROMPT = "You> "
    # Commands that exit the session
    EXIT_COMMANDS = frozenset({"exit", "quit", "bye", "q", ":q"})

    def __init__(
        self,
        agent: Optional[object] = None,
        user_id: str = "cli-user",
        session_id: Optional[str] = None,
        use_rich: bool = True,
    ) -> None:
        self.agent = agent
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self._use_rich = use_rich and _RICH_AVAILABLE
        self._active = False
        self._context: Optional[object] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_session(self) -> None:
        """Start an interactive REPL session.

        Displays a welcome banner, then enters a loop that reads user input,
        sends it to the agent via :meth:`send_message`, and prints the
        response.  The loop exits on EOF, :kbd:`Ctrl-C`, or when the user
        types an exit command.

        Requirement 10.1: Accept text commands from the user.
        Requirement 10.2: Display agent responses in readable format.
        Requirement 10.3: Support conversational sessions with maintained context.
        Requirement 10.4: Allow clean exit from the session.
        """
        self._active = True
        self._context = self._create_context()

        self._print_banner()

        while self._active:
            try:
                user_input = self._read_input()
            except (EOFError, KeyboardInterrupt):
                # Ctrl-D or Ctrl-C — exit gracefully (Requirement 10.4)
                self._print_info("\nSession interrupted. Goodbye!")
                break

            stripped = user_input.strip()
            if not stripped:
                continue

            if stripped.lower() in self.EXIT_COMMANDS:
                self.exit_session()
                break

            # Handle built-in commands
            if stripped.lower() in ("help", "?"):
                self._print_help()
                continue

            if stripped.lower() in ("resources", "list"):
                self._list_resources()
                continue

            # Forward to agent
            try:
                response = self.send_message(stripped)
                self._print_agent_response(response)
            except Exception as exc:  # noqa: BLE001
                self._print_error(f"Error: {exc}")
                logger.exception("Unexpected error while processing message: %s", exc)

    def send_message(self, message: str) -> str:
        """Send a message to the agent and return the response string.

        Requirement 10.1: Accept text commands from the user.
        Requirement 10.2: Display agent responses in readable format.

        Args:
            message: The user's natural language request.

        Returns:
            The agent's response as a plain string.

        Raises:
            RuntimeError: If no agent was provided at construction time.
        """
        if self.agent is None:
            raise RuntimeError(
                "No agent configured. Provide a BedrockIaCAgent instance to CLIInterface."
            )

        if self._context is None:
            self._context = self._create_context()

        # Import here to avoid circular imports at module level
        from .agent import BedrockIaCAgent  # noqa: PLC0415

        if not isinstance(self.agent, BedrockIaCAgent):
            raise TypeError(
                f"Expected a BedrockIaCAgent instance, got {type(self.agent).__name__}"
            )

        response = self.agent.process_request(message, self._context)  # type: ignore[arg-type]
        return response.message

    def display_progress(self, operation: str, status: str) -> None:
        """Display a progress indicator for a long-running operation.

        Requirement 10.5: Show progress indicators during long operations
        (cloning, push, PR creation).

        Args:
            operation: Human-readable name of the operation (e.g. "Cloning repository").
            status: Current status string (e.g. "in_progress", "done", "failed").
        """
        status_lower = status.lower()

        if self._use_rich:
            if status_lower in ("done", "success", "complete", "completed"):
                _console.print(f"  [agent]✓[/agent] {operation} — [agent]{status}[/agent]")
            elif status_lower in ("failed", "error"):
                _err_console.print(f"  [error]✗[/error] {operation} — [error]{status}[/error]")
            else:
                _console.print(f"  [progress]⟳[/progress] {operation} — [progress]{status}[/progress]")
        else:
            symbol = "✓" if status_lower in ("done", "success", "complete", "completed") else (
                "✗" if status_lower in ("failed", "error") else "⟳"
            )
            click.echo(f"  {symbol} {operation} — {status}")

    def exit_session(self) -> None:
        """Cleanly shut down the CLI session.

        Requirement 10.4: Allow clean exit from the session.
        """
        self._active = False
        self._print_info("Goodbye! Session ended.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_context(self) -> object:
        """Create a new ConversationContext for this session."""
        from .models import ConversationContext  # noqa: PLC0415

        return ConversationContext(
            session_id=self.session_id,
            user_id=self.user_id,
        )

    def _read_input(self) -> str:
        """Read a line of input from the user."""
        if self._use_rich:
            _console.print(f"[user]{self.PROMPT}[/user]", end="")
            return input()
        return input(self.PROMPT)

    def _print_banner(self) -> None:
        """Print the welcome banner."""
        banner_text = (
            "Bedrock IaC Agent\n"
            "─────────────────────────────────────────────────────\n"
            "Describe the AWS infrastructure you need in plain language.\n"
            "Type 'help' for available commands, or 'exit' to quit."
        )
        if self._use_rich:
            _console.print(
                Panel(
                    Text(banner_text, style="banner"),
                    title="[bold magenta]Welcome[/bold magenta]",
                    border_style="magenta",
                )
            )
        else:
            click.echo("=" * 55)
            click.echo(banner_text)
            click.echo("=" * 55)

    def _print_agent_response(self, response: str) -> None:
        """Print the agent's response with formatting."""
        if self._use_rich:
            _console.print(f"\n[agent]Agent>[/agent] {response}\n")
        else:
            click.echo(f"\nAgent> {response}\n")

    def _print_error(self, message: str) -> None:
        """Print an error message in red."""
        if self._use_rich:
            _err_console.print(f"[error]{message}[/error]")
        else:
            click.echo(f"ERROR: {message}", err=True)

    def _print_info(self, message: str) -> None:
        """Print an informational message."""
        if self._use_rich:
            _console.print(f"[info]{message}[/info]")
        else:
            click.echo(message)

    def _print_help(self) -> None:
        """Print available commands."""
        help_text = (
            "Available commands:\n"
            "  help / ?          Show this help message\n"
            "  resources / list  List available Golden Module resource types\n"
            "  exit / quit / q   Exit the session\n\n"
            "Or just type your infrastructure request in plain language, e.g.:\n"
            "  'Create an S3 bucket for storing logs in development'\n"
            "  'I need a Lambda function for the staging environment'"
        )
        if self._use_rich:
            _console.print(Panel(help_text, title="[bold]Help[/bold]", border_style="cyan"))
        else:
            click.echo(help_text)

    def _list_resources(self) -> None:
        """List available resource types from the agent."""
        if self.agent is None:
            self._print_info("No agent configured — cannot list resources.")
            return

        try:
            from .agent import BedrockIaCAgent  # noqa: PLC0415

            if isinstance(self.agent, BedrockIaCAgent):
                resources = self.agent.get_available_resources()
                lines = [f"  • {rt.value}" for rt in resources]
                body = "\n".join(lines) if lines else "  (none)"
                if self._use_rich:
                    _console.print(
                        Panel(body, title="[bold]Available Resources[/bold]", border_style="green")
                    )
                else:
                    click.echo("Available resources:\n" + body)
        except Exception as exc:  # noqa: BLE001
            self._print_error(f"Could not retrieve resources: {exc}")


# ---------------------------------------------------------------------------
# Progress context manager helper
# ---------------------------------------------------------------------------


class ProgressIndicator:
    """Context manager that shows a spinner during a long operation.

    Uses Rich's :class:`~rich.progress.Progress` when available, otherwise
    prints a simple start/end message.

    Args:
        operation: Description of the operation being performed.
        cli: Optional :class:`CLIInterface` to call
            :meth:`~CLIInterface.display_progress` on completion.

    Example::

        with ProgressIndicator("Cloning repository", cli=my_cli):
            github.clone_repository(url)
    """

    def __init__(self, operation: str, cli: Optional[CLIInterface] = None) -> None:
        self.operation = operation
        self.cli = cli
        self._progress: Optional[object] = None
        self._task_id: Optional[object] = None

    def __enter__(self) -> "ProgressIndicator":
        if _RICH_AVAILABLE:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=_console,
                transient=True,
            )
            self._progress.__enter__()  # type: ignore[union-attr]
            self._task_id = self._progress.add_task(  # type: ignore[union-attr]
                f"[progress]{self.operation}…[/progress]", total=None
            )
        else:
            click.echo(f"  ⟳ {self.operation}…")
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if _RICH_AVAILABLE and self._progress is not None:
            self._progress.__exit__(exc_type, exc_val, exc_tb)  # type: ignore[union-attr]

        status = "failed" if exc_type is not None else "done"
        if self.cli is not None:
            self.cli.display_progress(self.operation, status)
        elif not _RICH_AVAILABLE:
            symbol = "✓" if status == "done" else "✗"
            click.echo(f"  {symbol} {self.operation} — {status}")


# ---------------------------------------------------------------------------
# Click entry point
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Bedrock IaC Agent — deploy AWS infrastructure with natural language."""
    if ctx.invoked_subcommand is None:
        # Default: start interactive session without a real agent
        # (agent wiring happens in the 'chat' subcommand)
        ctx.invoke(chat)


@main.command()
@click.option("--user-id", default="cli-user", help="User identifier for audit logging.")
@click.option("--session-id", default=None, help="Session identifier (auto-generated if omitted).")
@click.option(
    "--config",
    "config_path",
    envvar="BEDROCK_IAC_CONFIG",
    default=None,
    help="Path to config.yaml (or set BEDROCK_IAC_CONFIG env var).",
)
@click.option(
    "--github-token",
    envvar="GITHUB_TOKEN",
    default=None,
    help="GitHub personal access token (or set GITHUB_TOKEN env var).",
)
@click.option(
    "--github-org",
    envvar="GITHUB_ORG",
    default=None,
    help="GitHub organisation name (or set GITHUB_ORG env var).",
)
@click.option(
    "--github-repo",
    envvar="GITHUB_REPO",
    default=None,
    help="GitHub repository name (or set GITHUB_REPO env var).",
)
@click.option(
    "--github-repo-url",
    envvar="GITHUB_REPO_URL",
    default=None,
    help="Full HTTPS URL of the GitHub repository (or set GITHUB_REPO_URL env var).",
)
@click.option(
    "--bedrock-model-id",
    envvar="BEDROCK_MODEL_ID",
    default=None,
    help="AWS Bedrock model ID to use for NLP parsing.",
)
@click.option(
    "--aws-region",
    envvar="AWS_DEFAULT_REGION",
    default=None,
    help="AWS region for Bedrock API calls.",
)
@click.option(
    "--aws-profile",
    envvar="AWS_PROFILE",
    default=None,
    help="AWS named profile to use (or set AWS_PROFILE env var).",
)
def chat(
    user_id: str,
    session_id: Optional[str],
    config_path: Optional[str],
    github_token: Optional[str],
    github_org: Optional[str],
    github_repo: Optional[str],
    github_repo_url: Optional[str],
    bedrock_model_id: Optional[str],
    aws_region: Optional[str],
    aws_profile: Optional[str],
) -> None:
    """Start an interactive chat session with the Bedrock IaC Agent."""
    # Configure logging before building the agent so all components use the
    # correct log level and handlers from the start.
    _configure_logging_from_config(config_path)

    agent = _build_agent_or_none(
        config_path=config_path,
        github_token=github_token,
        github_org=github_org,
        github_repo=github_repo,
        github_repo_url=github_repo_url,
        bedrock_model_id=bedrock_model_id,
        aws_region=aws_region,
        aws_profile=aws_profile,
    )

    cli = CLIInterface(agent=agent, user_id=user_id, session_id=session_id)
    cli.start_session()


@main.command(name="list-resources")
@click.option(
    "--config",
    "config_path",
    envvar="BEDROCK_IAC_CONFIG",
    default=None,
    help="Path to config.yaml (or set BEDROCK_IAC_CONFIG env var).",
)
@click.option(
    "--bedrock-model-id",
    envvar="BEDROCK_MODEL_ID",
    default=None,
    help="AWS Bedrock model ID.",
)
@click.option(
    "--aws-region",
    envvar="AWS_DEFAULT_REGION",
    default=None,
    help="AWS region for Bedrock API calls.",
)
@click.option(
    "--aws-profile",
    envvar="AWS_PROFILE",
    default=None,
    help="AWS named profile to use (or set AWS_PROFILE env var).",
)
def list_resources_cmd(
    config_path: Optional[str],
    bedrock_model_id: Optional[str],
    aws_region: Optional[str],
    aws_profile: Optional[str],
) -> None:
    """List all available Golden Module resource types."""
    _configure_logging_from_config(config_path)
    agent = _build_agent_or_none(
        config_path=config_path,
        bedrock_model_id=bedrock_model_id,
        aws_region=aws_region,
        aws_profile=aws_profile,
    )
    if agent is None:
        click.echo("Agent not configured. Set required environment variables to enable.")
        sys.exit(1)

    cli = CLIInterface(agent=agent)
    cli._list_resources()


# ---------------------------------------------------------------------------
# Logging configuration helper
# ---------------------------------------------------------------------------


def _configure_logging_from_config(config_path: Optional[str] = None) -> None:
    """Load logging settings from config.yaml and call setup_logging().

    This is called once at CLI startup so that all subsequent log messages
    from every component use the configured level, handlers, and rotation
    policy.

    Args:
        config_path: Optional path to ``config.yaml``.  When ``None`` the
            :class:`~bedrock_iac_agent.config_manager.ConfigurationManager`
            searches default locations automatically.
    """
    try:
        from .config_manager import ConfigurationManager  # noqa: PLC0415
        from .logging_config import setup_logging  # noqa: PLC0415

        cfg_manager = ConfigurationManager(config_path=config_path)
        logging_cfg = cfg_manager.to_logging_config()
        setup_logging(logging_cfg)
    except Exception as exc:  # noqa: BLE001
        # Fall back to a basic INFO console setup so the CLI still works
        from .logging_config import setup_logging, LoggingConfig  # noqa: PLC0415

        setup_logging(LoggingConfig())
        logging.getLogger(__name__).debug(
            "Could not load logging config from file: %s — using defaults.", exc
        )


# ---------------------------------------------------------------------------
# Agent factory helper
# ---------------------------------------------------------------------------


def _build_agent_or_none(
    config_path: Optional[str] = None,
    github_token: Optional[str] = None,
    github_org: Optional[str] = None,
    github_repo: Optional[str] = None,
    github_repo_url: Optional[str] = None,
    bedrock_model_id: Optional[str] = None,
    aws_region: Optional[str] = None,
    aws_profile: Optional[str] = None,
) -> Optional[object]:
    """Attempt to construct a BedrockIaCAgent from the supplied configuration.

    Uses :class:`~bedrock_iac_agent.config_manager.ConfigurationManager` to
    load settings from ``config.yaml`` (if present) and environment variables.
    Explicit CLI arguments take precedence over both file and env-var values.

    Args:
        config_path: Optional path to a ``config.yaml`` file.  When ``None``
            the manager searches default locations automatically.
        github_token: GitHub personal access token.  Overrides config file and
            ``GITHUB_TOKEN`` environment variable.
        github_org: GitHub organisation name.  Overrides config and ``GITHUB_ORG``.
        github_repo: GitHub repository name.  Overrides config and ``GITHUB_REPO``.
        github_repo_url: Full HTTPS URL of the repository.  Overrides config and
            ``GITHUB_REPO_URL``.
        bedrock_model_id: AWS Bedrock model ID for NLP parsing.  Overrides config
            and ``BEDROCK_MODEL_ID``.
        aws_region: AWS region for Bedrock API calls.  Overrides config and
            ``AWS_DEFAULT_REGION``.
        aws_profile: AWS named profile (e.g. "dev", "prod").  Overrides config
            and ``AWS_PROFILE`` environment variable.

    Returns:
        A configured :class:`~bedrock_iac_agent.agent.BedrockIaCAgent` instance,
        or ``None`` if construction fails.
    """
    try:
        from .agent import BedrockIaCAgent  # noqa: PLC0415
        from .audit_logger import AuditLogger  # noqa: PLC0415
        from .config_manager import ConfigurationManager  # noqa: PLC0415
        from .configuration_generator import ConfigurationGenerator  # noqa: PLC0415
        from .golden_modules_inventory import GoldenModulesInventory  # noqa: PLC0415
        from .natural_language_parser import NaturalLanguageParser  # noqa: PLC0415

        # Load base configuration from file + env vars
        cfg_manager = ConfigurationManager(config_path=config_path)

        # Apply explicit CLI overrides (highest priority)
        if github_token:
            cfg_manager.config.github.token = github_token
        if github_org:
            cfg_manager.config.github.organization = github_org
        if github_repo:
            cfg_manager.config.github.repository = github_repo
        if github_repo_url:
            cfg_manager.config.github.repo_url = github_repo_url
        if bedrock_model_id:
            cfg_manager.config.bedrock.model_id = bedrock_model_id
        if aws_region:
            cfg_manager.config.bedrock.region = aws_region
        if aws_profile:
            cfg_manager.config.bedrock.aws_profile = aws_profile

        # Validate configuration
        errors = cfg_manager.validate()
        if errors:
            for err in errors:
                logger.warning("Configuration error: %s", err)

        # Build components using resolved configuration
        nlp_parser = NaturalLanguageParser(
            model_id=cfg_manager.bedrock.model_id,
            region_name=cfg_manager.bedrock.region,
            aws_profile=cfg_manager.bedrock.aws_profile,
        )
        config_generator = ConfigurationGenerator()
        modules_inventory = GoldenModulesInventory()
        audit_logger = AuditLogger()

        # Naming conventions from config
        naming_conventions = cfg_manager.to_naming_conventions()

        # Wire up GitHub integration only when full credentials are available
        github_integration = None
        resolved_repo_url = cfg_manager.github.repo_url
        credentials = cfg_manager.to_github_credentials()

        if credentials is not None:
            from .github_integration import GitHubIntegration  # noqa: PLC0415

            github_integration = GitHubIntegration(
                credentials=credentials,
                audit_logger=audit_logger,
            )
        elif any([
            cfg_manager.github.token,
            cfg_manager.github.organization,
            cfg_manager.github.repository,
        ]):
            # Partial credentials — warn the user
            logger.warning(
                "GitHub integration requires github.token, github.organization, and "
                "github.repository (or GITHUB_TOKEN, GITHUB_ORG, GITHUB_REPO env vars). "
                "GitHub operations will be disabled until all three are provided."
            )

        return BedrockIaCAgent(
            nlp_parser=nlp_parser,
            config_generator=config_generator,
            github_integration=github_integration,
            modules_inventory=modules_inventory,
            audit_logger=audit_logger,
            naming_conventions=naming_conventions,
            repo_url=resolved_repo_url,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not build agent: %s", exc)
        return None


if __name__ == "__main__":
    main()
