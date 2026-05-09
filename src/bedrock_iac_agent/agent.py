"""Bedrock IaC Agent orchestrator.

This module implements the main BedrockIaCAgent class that orchestrates the
complete workflow from natural language input to Pull Request creation.

Pipeline:
    User Input → NaturalLanguageParser → ConfigurationGenerator → GitHubIntegration → PR

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 7.1, 7.2, 7.3, 7.4, 13.1, 13.2, 13.3, 13.4
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .audit_logger import AuditLogger
from .configuration_generator import ConfigurationGenerator
from .errors import (
    AgentError,
    AuthenticationError,
    GenerationError,
    ModuleNotFoundError,
    NetworkError,
    RepositoryError,
    ValidationError,
)
from .github_integration import GitHubIntegration
from .golden_modules_inventory import GoldenModulesInventory
from .models import (
    AgentResponse,
    ConversationContext,
    FileChange,
    GitHubCredentials,
    NamingConventions,
    PullRequestDetails,
    ResourceType,
    StructuredRequest,
    ValidationResult,
)
from .natural_language_parser import NaturalLanguageParser

logger = logging.getLogger(__name__)


class BedrockIaCAgent:
    """Orchestrates the complete IaC workflow from natural language to Pull Request.

    This class is the central coordinator of the Bedrock IaC Agent system.  It
    wires together the four main components:

    1. :class:`~bedrock_iac_agent.natural_language_parser.NaturalLanguageParser`
       — interprets the user's natural language request.
    2. :class:`~bedrock_iac_agent.golden_modules_inventory.GoldenModulesInventory`
       — provides the Golden Module schemas.
    3. :class:`~bedrock_iac_agent.configuration_generator.ConfigurationGenerator`
       — generates the Terraform tfvars file.
    4. :class:`~bedrock_iac_agent.github_integration.GitHubIntegration`
       — creates the branch, commits the file, and opens the Pull Request.

    Conversation context is maintained across multiple turns so that users can
    make iterative requests without repeating information (Requirements 13.1–13.4).

    Args:
        nlp_parser: Configured :class:`NaturalLanguageParser` instance.
        config_generator: Configured :class:`ConfigurationGenerator` instance.
        github_integration: Configured :class:`GitHubIntegration` instance.
            Pass ``None`` to disable GitHub operations (useful for testing).
        modules_inventory: Configured :class:`GoldenModulesInventory` instance.
        audit_logger: Optional :class:`AuditLogger` for structured logging.
        naming_conventions: Optional :class:`NamingConventions` to apply when
            generating tfvars.  Uses the generator's defaults when ``None``.
        repo_url: HTTPS URL of the base repository to clone.  Required when
            *github_integration* is provided.
        target_branch: The base branch for Pull Requests (default: ``"main"``).
        pr_labels: Labels to apply to created Pull Requests.
        pr_reviewers: GitHub usernames to request as reviewers.
        require_confirmation: When ``True``, the agent will ask the user to
            confirm before creating the Pull Request (Requirement 13.4).
    """

    def __init__(
        self,
        nlp_parser: NaturalLanguageParser,
        config_generator: ConfigurationGenerator,
        github_integration: Optional[GitHubIntegration] = None,
        modules_inventory: Optional[GoldenModulesInventory] = None,
        audit_logger: Optional[AuditLogger] = None,
        naming_conventions: Optional[NamingConventions] = None,
        repo_url: Optional[str] = None,
        target_branch: str = "main",
        pr_labels: Optional[List[str]] = None,
        pr_reviewers: Optional[List[str]] = None,
        require_confirmation: bool = False,
    ) -> None:
        self.nlp_parser = nlp_parser
        self.config_generator = config_generator
        self.github_integration = github_integration
        self.modules_inventory = modules_inventory or GoldenModulesInventory()
        self.audit_logger = audit_logger or AuditLogger()
        self.naming_conventions = naming_conventions
        self.repo_url = repo_url
        self.target_branch = target_branch
        self.pr_labels = pr_labels or ["iac-agent", "terraform"]
        self.pr_reviewers = pr_reviewers or []
        self.require_confirmation = require_confirmation

        # Internal state: maps session_id → ConversationContext
        self._sessions: Dict[str, ConversationContext] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_request(
        self,
        user_input: str,
        context: ConversationContext,
    ) -> AgentResponse:
        """Process a natural language infrastructure request end-to-end.

        Orchestrates the full pipeline:
        1. Log the incoming request (Requirement 14.1).
        2. Update conversation history (Requirement 13.1).
        3. Handle any pending clarifications first.
        4. Parse the natural language input via :class:`NaturalLanguageParser`.
        5. Check whether clarification is needed (Requirement 1.4).
        6. Validate the structured request (Requirements 1.1–1.5, 9.2).
        7. Generate the tfvars file (Requirements 3.1–3.6).
        8. Optionally ask for confirmation (Requirement 13.4).
        9. Create the GitHub branch, commit, and Pull Request (Requirements 5–6).
        10. Notify the user with the PR URL and next steps (Requirements 7.1–7.4).

        Args:
            user_input: The natural language request from the user.
            context: The current :class:`ConversationContext` for this session.

        Returns:
            :class:`AgentResponse` with status, message, PR URL, and next steps.
        """
        # Persist the context so we can look it up by session_id later
        self._sessions[context.session_id] = context

        # Log the incoming request (Requirement 14.1)
        self.audit_logger.log_request(
            user_id=context.user_id,
            request=user_input,
            timestamp=datetime.now(timezone.utc),
        )

        # Append user message to conversation history (Requirement 13.1)
        context.history.append({"role": "user", "content": user_input})

        try:
            # --- Handle pending clarifications (Requirement 13.2) ---
            if context.pending_clarifications:
                return self._handle_clarification_response(user_input, context)

            # --- Handle confirmation flow (Requirement 13.4) ---
            if context.current_request is not None and self.require_confirmation:
                return self._handle_confirmation(user_input, context)

            # --- Parse natural language (Requirements 1.1–1.5) ---
            structured_request = self.nlp_parser.parse(user_input, context)
            context.current_request = structured_request

            # --- Check for clarification (Requirement 1.4) ---
            clarification_question = self.nlp_parser.needs_clarification(structured_request)
            if clarification_question:
                context.pending_clarifications.append(clarification_question)
                response = self._build_needs_clarification_response(
                    clarification_question,
                    structured_request.request_id,
                )
                context.history.append({"role": "assistant", "content": response.message})
                return response

            # --- Validate the request (Requirements 9.2, 11.2, 11.3) ---
            validation_result = self.validate_request(structured_request)
            if not validation_result.is_valid:
                error_msg = (
                    "Your request could not be validated:\n"
                    + "\n".join(f"  • {e}" for e in validation_result.errors)
                )
                if validation_result.warnings:
                    error_msg += "\n\nWarnings:\n" + "\n".join(
                        f"  ⚠ {w}" for w in validation_result.warnings
                    )
                response = AgentResponse(
                    message=error_msg,
                    status="error",
                    next_steps=["Correct the issues above and try again."],
                    metadata={
                        "request_id": structured_request.request_id,
                        "errors": validation_result.errors,
                        "warnings": validation_result.warnings,
                    },
                )
                context.history.append({"role": "assistant", "content": response.message})
                return response

            # --- Generate tfvars (Requirements 3.1–3.6) ---
            golden_module = self.modules_inventory.get_module_schema(
                structured_request.resource_type
            )
            tfvars = self.config_generator.generate_tfvars(
                structured_request,
                golden_module,
                self.naming_conventions,
            )

            # Log the generated configuration (Requirement 14.2)
            self.audit_logger.log_configuration(structured_request, tfvars.content)

            # --- Confirmation gate (Requirement 13.4) ---
            if self.require_confirmation:
                summary = self._build_confirmation_summary(structured_request, tfvars)
                context.pending_clarifications.append("__awaiting_confirmation__")
                response = AgentResponse(
                    message=summary,
                    status="needs_clarification",
                    next_steps=[
                        "Reply 'yes' or 'confirm' to create the Pull Request.",
                        "Reply 'no' or 'cancel' to abort.",
                    ],
                    metadata={"request_id": structured_request.request_id},
                )
                context.history.append({"role": "assistant", "content": response.message})
                return response

            # --- Create GitHub PR (Requirements 5–6) ---
            pr_url = self._create_pull_request(structured_request, tfvars, context)

            # --- Build success response (Requirements 7.1–7.4) ---
            response = self._build_success_response(structured_request, pr_url)
            context.history.append({"role": "assistant", "content": response.message})

            # Clear current request after successful PR creation
            context.current_request = None
            context.pending_clarifications.clear()

            return response

        except ValidationError as exc:
            return self._handle_error(exc, context, "error")
        except ModuleNotFoundError as exc:
            alternatives = self.modules_inventory.suggest_alternatives(
                # We may not have a resource type if parsing failed; use a safe default
                getattr(exc, "_resource_type", ResourceType.S3_BUCKET)
            )
            alt_names = [rt.value for rt in alternatives]
            response = AgentResponse(
                message=(
                    f"{exc.error_message}\n\n"
                    + (
                        f"Similar resources you can use: {', '.join(alt_names)}"
                        if alt_names
                        else "Please check the list of available resources."
                    )
                ),
                status="error",
                next_steps=exc.suggested_actions,
                metadata={"suggested_alternatives": alt_names},
            )
            context.history.append({"role": "assistant", "content": response.message})
            return response
        except AuthenticationError as exc:
            return self._handle_error(exc, context, "error")
        except (NetworkError, RepositoryError) as exc:
            return self._handle_error(exc, context, "error")
        except GenerationError as exc:
            return self._handle_error(exc, context, "error")
        except AgentError as exc:
            return self._handle_error(exc, context, "error")
        except Exception as exc:
            # Catch-all: wrap unexpected errors (Requirement 12.5)
            logger.exception("Unexpected error in process_request: %s", exc)
            self.audit_logger.log_error(
                exc,
                {"operation": "process_request", "session_id": context.session_id},
                error_code="UNEXPECTED_ERROR",
            )
            response = AgentResponse(
                message=(
                    "Ocurrió un error inesperado al procesar tu solicitud. "
                    "Por favor intenta de nuevo o contacta soporte si el problema persiste."
                ),
                status="error",
                next_steps=["Intenta reformular tu solicitud.", "Contacta soporte si el problema persiste."],
                metadata={"error": str(exc)},
            )
            context.history.append({"role": "assistant", "content": response.message})
            return response

    def get_available_resources(self) -> List[ResourceType]:
        """Return the list of supported Golden Module resource types.

        Requirement 9.3: When a user requests information about available
        resources, list the supported types.

        Returns:
            List of :class:`ResourceType` enum values for all 12 Golden Modules.
        """
        modules = self.modules_inventory.list_available_modules()
        return [m.resource_type for m in modules]

    def validate_request(self, structured_request: StructuredRequest) -> ValidationResult:
        """Validate a structured request against available modules and security policies.

        Checks:
        - The requested resource type has a corresponding Golden Module (Req 9.2).
        - The module schema exists and is accessible (Req 12.4).
        - The supplied parameters pass the module's parameter validation (Req 12.3).
        - Security parameters are not being overridden (Req 11.2, 11.3).

        Args:
            structured_request: The parsed request to validate.

        Returns:
            :class:`ValidationResult` with ``is_valid``, ``errors``, and ``warnings``.
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Check that the resource type is supported (Requirement 9.2)
        module_info = self.modules_inventory.get_module(structured_request.resource_type)
        if module_info is None:
            alternatives = self.modules_inventory.suggest_alternatives(
                structured_request.resource_type
            )
            alt_str = (
                f" Consider: {', '.join(rt.value for rt in alternatives)}."
                if alternatives
                else ""
            )
            errors.append(
                f"Resource type '{structured_request.resource_type.value}' is not supported "
                f"by any available Golden Module.{alt_str}"
            )
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # Retrieve the module schema (may raise ModuleNotFoundError — let it propagate)
        try:
            golden_module = self.modules_inventory.get_module_schema(
                structured_request.resource_type
            )
        except ModuleNotFoundError as exc:
            errors.append(exc.error_message)
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # Validate parameters against the module schema (Requirement 12.3)
        param_validation = self.config_generator.validate_parameters(
            structured_request.parameters, golden_module
        )
        errors.extend(param_validation.errors)
        warnings.extend(param_validation.warnings)

        # Check for security parameter overrides (Requirements 11.2, 11.3)
        security_param_names = {p.name for p in golden_module.security_parameters}
        for param_name in structured_request.parameters:
            if param_name in security_param_names:
                warnings.append(
                    f"Security parameter '{param_name}' cannot be overridden. "
                    "The Golden Module's default value will be used."
                )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Conversation context helpers
    # ------------------------------------------------------------------

    def get_or_create_context(
        self,
        session_id: str,
        user_id: str,
        preferences: Optional[Dict[str, Any]] = None,
    ) -> ConversationContext:
        """Retrieve an existing session context or create a new one.

        Args:
            session_id: Unique identifier for the session.
            user_id: Identifier for the user (e.g. email address).
            preferences: Optional initial preferences for a new session.

        Returns:
            The :class:`ConversationContext` for the session.
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationContext(
                session_id=session_id,
                user_id=user_id,
                preferences=preferences or {},
            )
        return self._sessions[session_id]

    def clear_session(self, session_id: str) -> None:
        """Remove a session context from memory.

        Args:
            session_id: The session to clear.
        """
        self._sessions.pop(session_id, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_clarification_response(
        self,
        user_input: str,
        context: ConversationContext,
    ) -> AgentResponse:
        """Handle a user reply to a pending clarification question.

        When the agent previously asked a clarification question, the next
        user message is treated as the answer.  The clarification is removed
        from the queue and the request is re-processed with the enriched input.

        Args:
            user_input: The user's clarification answer.
            context: Current conversation context.

        Returns:
            :class:`AgentResponse` from re-processing the enriched request.
        """
        # Pop the first pending clarification
        context.pending_clarifications.pop(0)

        # If this was a confirmation gate, handle it separately
        if user_input.strip().lower() in ("yes", "y", "confirm", "ok", "proceed"):
            if context.current_request is not None:
                return self._execute_pr_creation(context.current_request, context)
            # No current request — fall through to re-parse
        elif user_input.strip().lower() in ("no", "n", "cancel", "abort"):
            context.current_request = None
            response = AgentResponse(
                message="Creación del Pull Request cancelada. Avísame cuando quieras empezar de nuevo.",
                status="success",
                next_steps=["Inicia una nueva solicitud cuando estés listo."],
            )
            context.history.append({"role": "assistant", "content": response.message})
            return response

        # Merge the clarification answer with the previous user message for re-parsing
        previous_user_messages = [
            m["content"] for m in context.history if m["role"] == "user"
        ]
        # Build an enriched prompt from the last substantive user message + clarification
        if len(previous_user_messages) >= 2:
            original_request = previous_user_messages[-2]  # -1 is the current answer
            enriched_input = f"{original_request}. {user_input}"
        else:
            enriched_input = user_input

        # Re-process with the enriched input (clear pending clarifications first)
        context.pending_clarifications.clear()
        context.current_request = None
        return self.process_request(enriched_input, context)

    def _handle_confirmation(
        self,
        user_input: str,
        context: ConversationContext,
    ) -> AgentResponse:
        """Handle a confirmation response when require_confirmation is True.

        Args:
            user_input: The user's confirmation answer.
            context: Current conversation context.

        Returns:
            :class:`AgentResponse` based on the user's answer.
        """
        answer = user_input.strip().lower()
        if answer in ("yes", "y", "confirm", "ok", "proceed"):
            assert context.current_request is not None
            return self._execute_pr_creation(context.current_request, context)
        elif answer in ("no", "n", "cancel", "abort"):
            context.current_request = None
            response = AgentResponse(
                message="Creación del Pull Request cancelada. Avísame cuando quieras empezar de nuevo.",
                status="success",
                next_steps=["Inicia una nueva solicitud cuando estés listo."],
            )
            context.history.append({"role": "assistant", "content": response.message})
            return response
        else:
            # Treat as a new request
            context.current_request = None
            return self.process_request(user_input, context)

    def _execute_pr_creation(
        self,
        structured_request: StructuredRequest,
        context: ConversationContext,
    ) -> AgentResponse:
        """Execute the PR creation step for a confirmed request.

        Args:
            structured_request: The validated and confirmed request.
            context: Current conversation context.

        Returns:
            :class:`AgentResponse` with the PR URL on success.
        """
        try:
            golden_module = self.modules_inventory.get_module_schema(
                structured_request.resource_type
            )
            tfvars = self.config_generator.generate_tfvars(
                structured_request,
                golden_module,
                self.naming_conventions,
            )
            self.audit_logger.log_configuration(structured_request, tfvars.content)
            pr_url = self._create_pull_request(structured_request, tfvars, context)
            response = self._build_success_response(structured_request, pr_url)
            context.history.append({"role": "assistant", "content": response.message})
            context.current_request = None
            context.pending_clarifications.clear()
            return response
        except AgentError as exc:
            return self._handle_error(exc, context, "error")
        except Exception as exc:
            logger.exception("Unexpected error during PR creation: %s", exc)
            response = AgentResponse(
                message=(
                    "Ocurrió un error inesperado al crear el Pull Request. "
                    "Por favor intenta de nuevo."
                ),
                status="error",
                next_steps=["Intenta de nuevo o contacta soporte."],
                metadata={"error": str(exc)},
            )
            context.history.append({"role": "assistant", "content": response.message})
            return response

    def _create_pull_request(
        self,
        structured_request: StructuredRequest,
        tfvars: Any,
        context: ConversationContext,
    ) -> Optional[str]:
        """Clone the repo, commit the tfvars file, and open a Pull Request.

        Args:
            structured_request: The validated request.
            tfvars: The generated :class:`~bedrock_iac_agent.models.TfvarsContent`.
            context: Current conversation context.

        Returns:
            The URL of the created Pull Request, or ``None`` if GitHub integration
            is not configured.

        Raises:
            AuthenticationError: If GitHub authentication fails.
            NetworkError: If network operations fail after retries.
            RepositoryError: If repository operations fail.
        """
        if self.github_integration is None or self.repo_url is None:
            logger.info(
                "GitHub integration not configured — skipping PR creation for request %s",
                structured_request.request_id,
            )
            return None

        # Authenticate (Requirement 5.2)
        self.github_integration.authenticate()

        # Clone the base repository (Requirement 5.1)
        repo = self.github_integration.clone_repository(self.repo_url)

        # Build a descriptive branch name (Requirement 5.3)
        branch_name = GitHubIntegration.build_branch_name(
            resource_type=structured_request.resource_type.value,
            environment=structured_request.environment.value,
        )
        branch = self.github_integration.create_branch(repo, branch_name)

        # Commit the tfvars file (Requirement 5.4)
        file_change = FileChange(
            file_path=tfvars.file_path,
            content=tfvars.content,
            operation="add",
        )
        commit_message = (
            f"feat(iac-agent): add {structured_request.resource_type.value} "
            f"tfvars for {structured_request.environment.value}\n\n"
            f"Request ID: {structured_request.request_id}\n"
            f"Requested by: {context.user_id}\n"
            f"Justification: {structured_request.user_justification}"
        )
        self.github_integration.commit_changes(repo, [file_change], commit_message)

        # Push the branch (Requirement 5.5)
        self.github_integration.push_branch(repo, branch)

        # Build PR details (Requirements 6.2–6.4)
        pr_title = (
            f"[IaC Agent] Add {structured_request.resource_type.value} "
            f"for {structured_request.environment.value}"
        )
        pr_details = PullRequestDetails(
            title=pr_title,
            description=structured_request.user_justification,
            source_branch=branch_name,
            target_branch=self.target_branch,
            labels=self.pr_labels,
            reviewers=self.pr_reviewers,
            metadata={
                "resource_type": structured_request.resource_type.value,
                "environment": structured_request.environment.value,
                "user_id": context.user_id,
                "request_id": structured_request.request_id,
                "conversation_id": context.session_id,
                "timestamp": structured_request.timestamp.isoformat(),
                "justification": structured_request.user_justification,
                "parameters": structured_request.parameters,
            },
        )

        # Create the Pull Request (Requirement 6.1)
        pull_request = self.github_integration.create_pull_request(branch, pr_details)

        # Log the PR creation (Requirement 14.3)
        self.audit_logger.log_pull_request(
            pr_url=pull_request.url,
            request_id=structured_request.request_id,
            resource_type=structured_request.resource_type,
            environment=structured_request.environment,
        )

        return pull_request.url

    def _build_success_response(
        self,
        structured_request: StructuredRequest,
        pr_url: Optional[str],
    ) -> AgentResponse:
        """Build a user-friendly success response.

        Requirements 7.1–7.3: Notify user with PR URL, summary of changes made,
        and next steps required (review, approval, merge).

        Args:
            structured_request: The completed request.
            pr_url: URL of the created Pull Request (or ``None`` if skipped).

        Returns:
            :class:`AgentResponse` with status ``"success"``.
        """
        resource = structured_request.resource_type.value
        env = structured_request.environment.value

        # Requirement 7.2: Provide a summary of the changes made
        changes_summary = self._format_changes_summary(structured_request)

        if pr_url:
            # Requirement 7.1: Notify user with the full PR URL
            message = (
                f"✅ ¡Pull Request creado exitosamente!\n\n"
                f"Recurso: {resource}\n"
                f"Ambiente: {env}\n"
                f"URL del PR: {pr_url}\n\n"
                f"{changes_summary}"
            )
            # Requirement 7.3: Indicate next steps required
            next_steps = [
                f"Revisa el Pull Request en: {pr_url}",
                "Aprueba el PR después de verificar la configuración.",
                "Haz merge del PR para activar el pipeline de despliegue de Terraform.",
            ]
        else:
            message = (
                f"✅ ¡Configuración generada exitosamente!\n\n"
                f"Recurso: {resource}\n"
                f"Ambiente: {env}\n\n"
                f"{changes_summary}\n"
                "(Integración con GitHub no configurada — no se creó ningún PR.)"
            )
            next_steps = [
                "Configura la integración con GitHub para habilitar la creación automática de PRs.",
                "Revisa la configuración tfvars generada.",
            ]

        return AgentResponse(
            message=message,
            pr_url=pr_url,
            status="success",
            next_steps=next_steps,
            metadata={
                "request_id": structured_request.request_id,
                "resource_type": resource,
                "environment": env,
            },
        )

    def _format_changes_summary(self, structured_request: StructuredRequest) -> str:
        """Format a human-readable summary of the changes made.

        Requirement 7.2: Provide a summary of the changes made, including the
        resource type, environment, configured parameters, and justification.

        Args:
            structured_request: The completed request.

        Returns:
            A formatted multi-line string summarising the changes.
        """
        lines = ["Summary of changes:"]

        # Show configured parameters if any were provided
        if structured_request.parameters:
            lines.append("  Configured parameters:")
            for key, value in structured_request.parameters.items():
                lines.append(f"    • {key}: {value}")
        else:
            lines.append("  No custom parameters specified (using Golden Module defaults).")

        # Include the user's original justification
        if structured_request.user_justification:
            lines.append(f"  Justification: {structured_request.user_justification}")

        return "\n".join(lines)

    def _build_confirmation_summary(
        self,
        structured_request: StructuredRequest,
        tfvars: Any,
    ) -> str:
        """Build a human-readable summary for the confirmation prompt.

        Requirement 13.4: Allow user to confirm or cancel before PR creation.

        Args:
            structured_request: The request to summarise.
            tfvars: The generated tfvars content.

        Returns:
            A formatted summary string.
        """
        params_summary = "\n".join(
            f"  {k}: {v}" for k, v in structured_request.parameters.items()
        )
        return (
            f"I'm about to create a Pull Request with the following configuration:\n\n"
            f"Resource: {structured_request.resource_type.value}\n"
            f"Environment: {structured_request.environment.value}\n"
            f"File: {tfvars.file_path}\n"
            + (f"Parameters:\n{params_summary}\n" if params_summary else "")
            + f"\nJustification: {structured_request.user_justification}\n\n"
            "Reply 'yes' to confirm or 'no' to cancel."
        )

    def _build_needs_clarification_response(
        self,
        question: str,
        request_id: str,
    ) -> AgentResponse:
        """Build a response asking the user for clarification.

        Requirement 1.4: When the request contains ambiguous terms, ask for
        clarification before proceeding.

        Args:
            question: The clarification question to present to the user.
            request_id: The ID of the request requiring clarification.

        Returns:
            :class:`AgentResponse` with status ``"needs_clarification"``.
        """
        return AgentResponse(
            message=question,
            status="needs_clarification",
            next_steps=["Please answer the question above to continue."],
            metadata={"request_id": request_id},
        )

    def _handle_error(
        self,
        exc: AgentError,
        context: ConversationContext,
        status: str,
    ) -> AgentResponse:
        """Build an error response from an :class:`AgentError`.

        Requirement 7.4: Inform user with a descriptive error message and
        suggested corrective actions so they know how to resolve the issue.

        Args:
            exc: The agent error that occurred.
            context: Current conversation context.
            status: Response status string (usually ``"error"``).

        Returns:
            :class:`AgentResponse` with status ``"error"``.
        """
        self.audit_logger.log_error(
            exc,
            {"operation": "process_request", "session_id": context.session_id},
            error_code=exc.error_code,
        )

        # Requirement 7.4: Always provide at least one corrective action
        next_steps = list(exc.suggested_actions) if exc.suggested_actions else [
            "Review the error message above and try again.",
            "Contact support if the issue persists.",
        ]

        response = AgentResponse(
            message=exc.error_message,
            status=status,
            next_steps=next_steps,
            metadata={
                "error_code": exc.error_code,
                "retry_possible": exc.retry_possible,
            },
        )
        context.history.append({"role": "assistant", "content": response.message})
        return response
