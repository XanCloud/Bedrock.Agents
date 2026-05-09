"""Configuration management for the Bedrock IaC Agent.

Loads and validates agent configuration from a ``config.yaml`` file and
environment variables.  Environment variables always take precedence over
file-based values so that sensitive credentials (tokens, keys) can be
injected at runtime without being stored on disk.

Supported configuration schema (all sections are optional):

.. code-block:: yaml

    github:
      token: "ghp_..."          # overridden by GITHUB_TOKEN env var
      organization: "my-org"    # overridden by GITHUB_ORG
      repository: "my-repo"     # overridden by GITHUB_REPO
      repo_url: "https://..."   # overridden by GITHUB_REPO_URL

    bedrock:
      model_id: "anthropic.claude-3-haiku-20240307-v1:0"  # BEDROCK_MODEL_ID
      region: "us-east-1"       # AWS_REGION / AWS_DEFAULT_REGION
      aws_profile: null         # AWS_PROFILE

    naming:
      prefix: ""
      environment_suffix: true
      separator: "-"
      max_length: 63
      allowed_characters: "[a-z0-9\\-]"

    logging:
      level: INFO                # LOG_LEVEL env var
      console:
        enabled: true
        level: INFO
      file:
        enabled: false           # LOG_FILE_ENABLED env var
        path: logs/bedrock-iac-agent.log  # LOG_FILE env var
        level: DEBUG
        rotation:
          enabled: true
          max_bytes: 10485760    # 10 MB
          backup_count: 5

Requirements: 5.2, 8.4, 11.4
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typed configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass
class GitHubConfig:
    """GitHub credentials and repository settings."""

    token: Optional[str] = None
    organization: Optional[str] = None
    repository: Optional[str] = None
    repo_url: Optional[str] = None


@dataclass
class BedrockConfig:
    """AWS Bedrock model and region settings."""

    model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    region: str = "us-east-1"
    aws_profile: Optional[str] = None


@dataclass
class NamingConfig:
    """Naming convention settings for generated resources."""

    prefix: str = ""
    environment_suffix: bool = True
    separator: str = "-"
    max_length: int = 63
    allowed_characters: str = r"[a-z0-9\-]"


@dataclass
class AgentConfig:
    """Top-level agent configuration aggregating all sub-sections."""

    github: GitHubConfig = field(default_factory=GitHubConfig)
    bedrock: BedrockConfig = field(default_factory=BedrockConfig)
    naming: NamingConfig = field(default_factory=NamingConfig)
    logging: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ConfigurationManager
# ---------------------------------------------------------------------------


class ConfigurationManager:
    """Loads, validates, and exposes agent configuration.

    Configuration is resolved in the following priority order (highest first):

    1. Environment variables (e.g. ``GITHUB_TOKEN``, ``AWS_REGION``)
    2. Values from the ``config.yaml`` file
    3. Built-in defaults

    Args:
        config_path: Path to the ``config.yaml`` file.  When ``None`` the
            manager looks for ``config.yaml`` in the current working directory
            and then in ``~/.bedrock-iac-agent/config.yaml``.  If neither
            exists the manager starts with defaults only.

    Raises:
        ConfigurationError: If the config file exists but cannot be parsed or
            contains invalid values.

    Requirements: 5.2, 8.4, 11.4
    """

    # Environment variable → (section, key) mapping
    _ENV_MAP: Dict[str, tuple[str, str]] = {
        "GITHUB_TOKEN": ("github", "token"),
        "GITHUB_ORG": ("github", "organization"),
        "GITHUB_REPO": ("github", "repository"),
        "GITHUB_REPO_URL": ("github", "repo_url"),
        "BEDROCK_MODEL_ID": ("bedrock", "model_id"),
        "AWS_REGION": ("bedrock", "region"),
        "AWS_DEFAULT_REGION": ("bedrock", "region"),
        "AWS_PROFILE": ("bedrock", "aws_profile"),
    }

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._config_path = self._resolve_config_path(config_path)
        self._raw: Dict[str, Any] = {}
        self.config: AgentConfig = AgentConfig()
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def github(self) -> GitHubConfig:
        """GitHub credentials and repository settings."""
        return self.config.github

    @property
    def bedrock(self) -> BedrockConfig:
        """Bedrock model and region settings."""
        return self.config.bedrock

    @property
    def naming(self) -> NamingConfig:
        """Naming convention settings."""
        return self.config.naming

    def validate(self) -> list[str]:
        """Validate the loaded configuration and return a list of error messages.

        Returns an empty list when the configuration is valid.

        Checks:
        - ``bedrock.model_id`` is a non-empty string.
        - ``bedrock.region`` is a non-empty string.
        - ``naming.max_length`` is a positive integer.
        - ``naming.separator`` is a single non-empty character.

        Returns:
            List of human-readable error strings.  Empty when valid.
        """
        errors: list[str] = []

        if not self.config.bedrock.model_id:
            errors.append("bedrock.model_id must not be empty.")

        if not self.config.bedrock.region:
            errors.append("bedrock.region must not be empty.")

        if self.config.naming.max_length <= 0:
            errors.append("naming.max_length must be a positive integer.")

        if not self.config.naming.separator:
            errors.append("naming.separator must not be empty.")

        return errors

    def to_naming_conventions(self) -> "NamingConventions":  # type: ignore[name-defined]
        """Convert the naming config to a :class:`~bedrock_iac_agent.models.NamingConventions`.

        Returns:
            A :class:`~bedrock_iac_agent.models.NamingConventions` dataclass
            populated from the current naming configuration.
        """
        from .models import NamingConventions  # noqa: PLC0415

        return NamingConventions(
            prefix=self.config.naming.prefix,
            environment_suffix=self.config.naming.environment_suffix,
            separator=self.config.naming.separator,
            max_length=self.config.naming.max_length,
            allowed_characters=self.config.naming.allowed_characters,
        )

    def to_logging_config(self) -> "LoggingConfig":  # type: ignore[name-defined]
        """Convert the raw logging config dict to a :class:`~bedrock_iac_agent.logging_config.LoggingConfig`.

        Returns:
            A :class:`~bedrock_iac_agent.logging_config.LoggingConfig` instance
            populated from the ``logging`` section of the config file (if any).
        """
        from .logging_config import logging_config_from_dict  # noqa: PLC0415

        return logging_config_from_dict(self.config.logging)

    def to_github_credentials(self) -> Optional["GitHubCredentials"]:  # type: ignore[name-defined]
        """Convert the GitHub config to a :class:`~bedrock_iac_agent.models.GitHubCredentials`.

        Returns:
            A :class:`~bedrock_iac_agent.models.GitHubCredentials` dataclass
            when all required fields (token, organization, repository) are
            present, otherwise ``None``.
        """
        gh = self.config.github
        if gh.token and gh.organization and gh.repository:
            from .models import GitHubCredentials  # noqa: PLC0415

            return GitHubCredentials(
                token=gh.token,
                organization=gh.organization,
                repository=gh.repository,
            )
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_config_path(self, config_path: Optional[str]) -> Optional[Path]:
        """Resolve the config file path, searching default locations if needed."""
        if config_path is not None:
            return Path(config_path)

        # Search default locations
        candidates = [
            Path.cwd() / "config.yaml",
            Path.home() / ".bedrock-iac-agent" / "config.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                logger.debug("Found config file at: %s", candidate)
                return candidate

        logger.debug("No config.yaml found; using defaults and environment variables only.")
        return None

    def _load(self) -> None:
        """Load configuration from file and environment variables."""
        # Step 1: Start with built-in defaults (already set in AgentConfig)
        raw: Dict[str, Any] = {}

        # Step 2: Load from file if available
        if self._config_path is not None and self._config_path.exists():
            raw = self._load_yaml(self._config_path)
            logger.info("Loaded configuration from: %s", self._config_path)

        # Step 3: Merge file values into config
        self._apply_raw(raw)

        # Step 4: Override with environment variables (highest priority)
        self._apply_env_vars()

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Parse a YAML config file and return the raw dictionary.

        Raises:
            ConfigurationError: If the file cannot be parsed.
        """
        try:
            import yaml  # noqa: PLC0415

            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ConfigurationError(
                    f"Config file {path} must contain a YAML mapping at the top level, "
                    f"got {type(data).__name__}."
                )
            return data
        except ImportError as exc:
            raise ConfigurationError(
                "PyYAML is required to load config.yaml. "
                "Install it with: pip install pyyaml"
            ) from exc
        except Exception as exc:
            if isinstance(exc, ConfigurationError):
                raise
            raise ConfigurationError(
                f"Failed to parse config file {path}: {exc}"
            ) from exc

    def _apply_raw(self, raw: Dict[str, Any]) -> None:
        """Merge raw YAML dictionary values into the typed config."""
        # GitHub section
        gh_raw = raw.get("github", {}) or {}
        if isinstance(gh_raw, dict):
            if "token" in gh_raw:
                self.config.github.token = str(gh_raw["token"])
            if "organization" in gh_raw:
                self.config.github.organization = str(gh_raw["organization"])
            if "repository" in gh_raw:
                self.config.github.repository = str(gh_raw["repository"])
            if "repo_url" in gh_raw:
                self.config.github.repo_url = str(gh_raw["repo_url"])

        # Bedrock section
        bedrock_raw = raw.get("bedrock", {}) or {}
        if isinstance(bedrock_raw, dict):
            if "model_id" in bedrock_raw:
                self.config.bedrock.model_id = str(bedrock_raw["model_id"])
            if "region" in bedrock_raw:
                self.config.bedrock.region = str(bedrock_raw["region"])
            if "aws_profile" in bedrock_raw:
                val = bedrock_raw["aws_profile"]
                self.config.bedrock.aws_profile = str(val) if val is not None else None

        # Naming section
        naming_raw = raw.get("naming", {}) or {}
        if isinstance(naming_raw, dict):
            if "prefix" in naming_raw:
                self.config.naming.prefix = str(naming_raw["prefix"])
            if "environment_suffix" in naming_raw:
                self.config.naming.environment_suffix = bool(naming_raw["environment_suffix"])
            if "separator" in naming_raw:
                self.config.naming.separator = str(naming_raw["separator"])
            if "max_length" in naming_raw:
                self.config.naming.max_length = int(naming_raw["max_length"])
            if "allowed_characters" in naming_raw:
                self.config.naming.allowed_characters = str(naming_raw["allowed_characters"])

        # Logging section — stored as raw dict; parsed by logging_config_from_dict()
        logging_raw = raw.get("logging", {}) or {}
        if isinstance(logging_raw, dict):
            self.config.logging = logging_raw

    def _apply_env_vars(self) -> None:
        """Override config values with environment variables."""
        for env_var, (section, key) in self._ENV_MAP.items():
            value = os.environ.get(env_var)
            if value is not None:
                section_obj = getattr(self.config, section)
                # Only override if the env var is non-empty
                if value:
                    setattr(section_obj, key, value)
                    logger.debug(
                        "Config override from env var %s → %s.%s", env_var, section, key
                    )


# ---------------------------------------------------------------------------
# ConfigurationError
# ---------------------------------------------------------------------------


class ConfigurationError(Exception):
    """Raised when the configuration file is invalid or cannot be loaded."""
