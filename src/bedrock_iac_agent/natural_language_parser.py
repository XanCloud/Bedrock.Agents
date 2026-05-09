"""Natural Language Parser component for the Bedrock IaC Agent.

This module interprets natural language infrastructure requests and converts
them into structured configuration objects using AWS Bedrock economic models.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .errors import BedrockError, ValidationError
from .models import (
    ConversationContext,
    Environment,
    ResourceType,
    StructuredRequest,
    TechnologyType,
)

logger = logging.getLogger(__name__)

# Economic models ordered by cost (cheapest first)
ECONOMIC_MODELS: List[str] = [
    "anthropic.claude-3-haiku-20240307-v1:0",  # Primary - cheapest
    "amazon.nova-micro-v1:0",                   # Fallback option
    "amazon.nova-lite-v1:0",                    # Fallback option
]

# System prompt for infrastructure parsing
SYSTEM_PROMPT = """Eres un experto en análisis de solicitudes de infraestructura AWS.
Tu tarea es interpretar solicitudes en lenguaje natural (en cualquier idioma, principalmente español) y extraer información estructurada.

Extrae lo siguiente de la solicitud del usuario:
1. resource_type: El tipo de recurso AWS solicitado. Debe ser uno de:
   - s3_bucket (bucket S3, almacenamiento de objetos, almacenamiento de archivos)
   - ec2_instance (EC2, máquina virtual, VM, servidor, instancia de cómputo)
   - rds_database (RDS, base de datos relacional, MySQL, PostgreSQL, base de datos)
   - lambda_function (Lambda, función serverless, función, FaaS)
   - api_gateway (API Gateway, REST API, HTTP API, endpoint de API)
   - dynamodb_table (DynamoDB, base de datos NoSQL, almacén clave-valor)
   - vpc (VPC, nube privada virtual, red, networking)
   - security_group (grupo de seguridad, firewall, reglas de red)
   - iam_role (rol IAM, permisos, rol de acceso, rol de servicio)
   - cloudwatch_log_group (CloudWatch logs, grupo de logs, logging)
   - sns_topic (SNS, notificación, topic, pub/sub)
   - sqs_queue (SQS, cola, cola de mensajes, cola FIFO)

2. parameters: Parámetros de configuración mencionados en la solicitud (nombre, tamaño, tipo, etc.)

3. environment: El ambiente de despliegue. Debe ser uno de:
   - dev (desarrollo, development, develop, local, pruebas, test)
   - staging (staging, stage, pre-prod, pre-producción, uat)
   - prod (producción, production, live, productivo)

4. confidence: Un número entre 0.0 y 1.0 indicando tu nivel de confianza en la extracción.
   Usa valores bajos cuando la solicitud sea ambigua o falte información clave.

Responde ÚNICAMENTE con un objeto JSON válido en este formato exacto:
{
  "resource_type": "<valor_o_null>",
  "parameters": {<pares_clave_valor>},
  "environment": "<valor_o_null>",
  "confidence": <float_0_a_1>,
  "user_justification": "<resumen_breve_de_lo_que_quiere_el_usuario>"
}

Si no puedes determinar resource_type o environment, usa null y establece confidence por debajo de 0.7.
"""

# Few-shot examples covering all 12 resource types and all 3 environments
FEW_SHOT_EXAMPLES = [
    {
        "user": "I need an S3 bucket called data-lake for development",
        "assistant": json.dumps({
            "resource_type": "s3_bucket",
            "parameters": {"bucket_name": "data-lake"},
            "environment": "dev",
            "confidence": 0.98,
            "user_justification": "Create an S3 bucket named data-lake for development environment"
        })
    },
    {
        "user": "Create an EC2 instance of type t3.medium for production",
        "assistant": json.dumps({
            "resource_type": "ec2_instance",
            "parameters": {"instance_type": "t3.medium"},
            "environment": "prod",
            "confidence": 0.97,
            "user_justification": "Create a t3.medium EC2 instance for production environment"
        })
    },
    {
        "user": "Set up a PostgreSQL RDS database for staging",
        "assistant": json.dumps({
            "resource_type": "rds_database",
            "parameters": {"engine": "postgres"},
            "environment": "staging",
            "confidence": 0.95,
            "user_justification": "Create a PostgreSQL RDS database for staging environment"
        })
    },
    {
        "user": "Deploy a Python 3.11 Lambda function named image-processor in dev",
        "assistant": json.dumps({
            "resource_type": "lambda_function",
            "parameters": {"function_name": "image-processor", "runtime": "python3.11"},
            "environment": "dev",
            "confidence": 0.98,
            "user_justification": "Create a Python 3.11 Lambda function named image-processor for development"
        })
    },
    {
        "user": "I need an API Gateway for the production environment",
        "assistant": json.dumps({
            "resource_type": "api_gateway",
            "parameters": {},
            "environment": "prod",
            "confidence": 0.90,
            "user_justification": "Create an API Gateway for production environment"
        })
    },
    {
        "user": "Create a DynamoDB table called user-sessions for staging",
        "assistant": json.dumps({
            "resource_type": "dynamodb_table",
            "parameters": {"table_name": "user-sessions"},
            "environment": "staging",
            "confidence": 0.97,
            "user_justification": "Create a DynamoDB table named user-sessions for staging environment"
        })
    },
    {
        "user": "Set up a VPC for the development environment",
        "assistant": json.dumps({
            "resource_type": "vpc",
            "parameters": {},
            "environment": "dev",
            "confidence": 0.92,
            "user_justification": "Create a VPC for development environment"
        })
    },
    {
        "user": "Create a security group for web servers in production",
        "assistant": json.dumps({
            "resource_type": "security_group",
            "parameters": {"description": "Security group for web servers"},
            "environment": "prod",
            "confidence": 0.93,
            "user_justification": "Create a security group for web servers in production environment"
        })
    },
    {
        "user": "I need an IAM role for Lambda execution in staging",
        "assistant": json.dumps({
            "resource_type": "iam_role",
            "parameters": {"role_name": "lambda-execution"},
            "environment": "staging",
            "confidence": 0.94,
            "user_justification": "Create an IAM role for Lambda execution in staging environment"
        })
    },
    {
        "user": "Create a CloudWatch log group for application logs in dev",
        "assistant": json.dumps({
            "resource_type": "cloudwatch_log_group",
            "parameters": {"log_group_name": "application-logs"},
            "environment": "dev",
            "confidence": 0.95,
            "user_justification": "Create a CloudWatch log group for application logs in development"
        })
    },
    {
        "user": "Set up an SNS topic for order notifications in production",
        "assistant": json.dumps({
            "resource_type": "sns_topic",
            "parameters": {"topic_name": "order-notifications"},
            "environment": "prod",
            "confidence": 0.96,
            "user_justification": "Create an SNS topic for order notifications in production environment"
        })
    },
    {
        "user": "Create an SQS queue for processing jobs in staging",
        "assistant": json.dumps({
            "resource_type": "sqs_queue",
            "parameters": {"queue_name": "processing-jobs"},
            "environment": "staging",
            "confidence": 0.95,
            "user_justification": "Create an SQS queue for processing jobs in staging environment"
        })
    },
    {
        "user": "I need a database",
        "assistant": json.dumps({
            "resource_type": None,
            "parameters": {},
            "environment": None,
            "confidence": 0.40,
            "user_justification": "User wants a database but type and environment are unclear"
        })
    },
]


class NaturalLanguageParser:
    """
    Parses natural language infrastructure requests using AWS Bedrock economic models.

    This component interprets user requests in conversational language and extracts
    structured configuration information including resource type, parameters, and
    target environment.

    Attributes:
        model_id: The Bedrock model ID currently in use.
        auto_select: Whether to automatically select the cheapest available model.
        _bedrock_client: The boto3 Bedrock runtime client.
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        auto_select: bool = False,
        region_name: Optional[str] = None,
        audit_logger: Optional[Any] = None,
        aws_profile: Optional[str] = None,
    ) -> None:
        """
        Initialize the NaturalLanguageParser with Bedrock integration.

        Args:
            model_id: Specific Bedrock model ID to use. Defaults to the primary
                      economic model (Claude Haiku) if not specified.
            auto_select: If True, automatically selects the cheapest available model
                         by testing model availability in order of cost.
            region_name: AWS region for Bedrock client. Uses default region if None.
            audit_logger: Optional AuditLogger instance for structured error logging.
            aws_profile: AWS named profile to use (e.g. "dev", "prod"). When None,
                         uses the default credential chain.

        Raises:
            RuntimeError: If Bedrock client cannot be initialized.
        """
        self._region_name = region_name
        self._aws_profile = aws_profile
        self.audit_logger = audit_logger
        self._bedrock_client = self._initialize_bedrock_client()

        if auto_select:
            self.model_id = self._select_cheapest_model()
        elif model_id is not None:
            self.model_id = model_id
        else:
            self.model_id = ECONOMIC_MODELS[0]

        self.auto_select = auto_select
        logger.info(f"NaturalLanguageParser initialized with model: {self.model_id}")

    def _initialize_bedrock_client(self) -> Any:
        """
        Initialize the AWS Bedrock runtime client.

        Returns:
            boto3 Bedrock runtime client.

        Raises:
            RuntimeError: If the client cannot be created.
        """
        try:
            kwargs: Dict[str, Any] = {"service_name": "bedrock-runtime"}
            if self._region_name:
                kwargs["region_name"] = self._region_name
            if self._aws_profile:
                session = boto3.Session(
                    profile_name=self._aws_profile,
                    region_name=self._region_name,
                )
                return session.client("bedrock-runtime")
            return boto3.client(**kwargs)
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize Bedrock client: {e}. "
                "Ensure AWS credentials are configured and Bedrock is available."
            ) from e

    def _select_cheapest_model(self) -> str:
        """
        Select the cheapest available Bedrock model by testing availability.

        Iterates through economic models in order of cost (cheapest first) and
        returns the first one that is accessible.

        Returns:
            Model ID of the cheapest available model.
        """
        for model_id in ECONOMIC_MODELS:
            try:
                # Test model availability with a minimal request
                self._invoke_model(
                    model_id=model_id,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5,
                )
                logger.info(f"Selected model: {model_id} (cheapest available)")
                return model_id
            except (ClientError, BotoCoreError) as e:
                logger.warning(f"Model {model_id} not available: {e}. Trying next model.")
                continue

        # Fall back to primary model if none are reachable
        logger.warning(
            f"No models could be verified as available. Defaulting to {ECONOMIC_MODELS[0]}"
        )
        return ECONOMIC_MODELS[0]

    def get_selected_model(self) -> str:
        """
        Return the currently selected Bedrock model ID.

        Returns:
            The model ID string currently in use.
        """
        return self.model_id

    def _build_messages(self, user_input: str) -> List[Dict[str, Any]]:
        """
        Build the messages list with few-shot examples and the user's input.

        Args:
            user_input: The natural language request from the user.

        Returns:
            List of message dictionaries for the Bedrock API.
        """
        messages: List[Dict[str, Any]] = []

        # Add few-shot examples as conversation history
        for example in FEW_SHOT_EXAMPLES:
            messages.append({"role": "user", "content": example["user"]})
            messages.append({"role": "assistant", "content": example["assistant"]})

        # Add the actual user request
        messages.append({"role": "user", "content": user_input})

        return messages

    def _invoke_model(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """
        Invoke a Bedrock model with the given messages.

        Handles both Anthropic Claude and Amazon Nova model APIs.

        Args:
            model_id: The Bedrock model ID to invoke.
            messages: List of message dictionaries.
            max_tokens: Maximum tokens for the response.

        Returns:
            Parsed response dictionary from the model.

        Raises:
            ClientError: If the Bedrock API call fails.
            BotoCoreError: If there is a low-level AWS error.
        """
        # Build request body based on model provider
        if model_id.startswith("anthropic."):
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "system": SYSTEM_PROMPT,
                "messages": messages,
            }
        else:
            # Amazon Nova and other models use the converse-compatible format
            request_body = {
                "messages": messages,
                "system": [{"text": SYSTEM_PROMPT}],
                "inferenceConfig": {"maxTokens": max_tokens},
            }

        response = self._bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(request_body),
        )

        response_body = json.loads(response["body"].read())
        return response_body

    def _extract_text_from_response(
        self, response_body: Dict[str, Any], model_id: str
    ) -> str:
        """
        Extract the text content from a Bedrock model response.

        Args:
            response_body: The parsed response body from Bedrock.
            model_id: The model ID used (affects response format).

        Returns:
            The text content from the model response.

        Raises:
            ValueError: If the response format is unexpected.
        """
        if model_id.startswith("anthropic."):
            # Claude response format
            content = response_body.get("content", [])
            if content and isinstance(content, list):
                return content[0].get("text", "")
            raise ValueError(f"Unexpected Claude response format: {response_body}")
        else:
            # Amazon Nova response format
            output = response_body.get("output", {})
            message = output.get("message", {})
            content = message.get("content", [])
            if content and isinstance(content, list):
                return content[0].get("text", "")
            raise ValueError(f"Unexpected Nova response format: {response_body}")

    def _get_token_usage(
        self, response_body: Dict[str, Any], model_id: str
    ) -> Dict[str, int]:
        """
        Extract token usage information from a Bedrock response.

        Args:
            response_body: The parsed response body from Bedrock.
            model_id: The model ID used (affects response format).

        Returns:
            Dictionary with input_tokens and output_tokens counts.
        """
        if model_id.startswith("anthropic."):
            usage = response_body.get("usage", {})
            return {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }
        else:
            usage = response_body.get("usage", {})
            return {
                "input_tokens": usage.get("inputTokens", 0),
                "output_tokens": usage.get("outputTokens", 0),
            }

    def _parse_model_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse the JSON response from the model into a dictionary.

        Handles cases where the model wraps JSON in markdown code blocks.

        Args:
            response_text: The raw text response from the model.

        Returns:
            Parsed dictionary from the JSON response.

        Raises:
            ValueError: If the response cannot be parsed as valid JSON.
        """
        # Strip markdown code blocks if present
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            text = "\n".join(lines[1:-1]).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Model returned invalid JSON: {e}. Response was: {response_text[:200]}"
            ) from e

    def _call_bedrock_with_fallback(
        self, messages: List[Dict[str, Any]]
    ) -> tuple[Dict[str, Any], str, Dict[str, int]]:
        """
        Call Bedrock with automatic fallback to next model on failure.

        Tries each economic model in order until one succeeds.

        Args:
            messages: List of message dictionaries for the API.

        Returns:
            Tuple of (parsed_response_dict, model_id_used, token_usage).

        Raises:
            BedrockError: If all models fail (Requirement 12.5).
        """
        # Start with the configured model, then fall back to others
        models_to_try = [self.model_id] + [
            m for m in ECONOMIC_MODELS if m != self.model_id
        ]

        last_error: Optional[Exception] = None
        for model_id in models_to_try:
            try:
                response_body = self._invoke_model(model_id=model_id, messages=messages)
                response_text = self._extract_text_from_response(response_body, model_id)
                parsed = self._parse_model_response(response_text)
                token_usage = self._get_token_usage(response_body, model_id)

                # Log model usage for audit (Requirement 2.3)
                total_tokens = token_usage["input_tokens"] + token_usage["output_tokens"]
                logger.info(
                    "Bedrock model invoked",
                    extra={
                        "event_type": "model_usage",
                        "model_used": model_id,
                        "tokens_consumed": total_tokens,
                        "input_tokens": token_usage["input_tokens"],
                        "output_tokens": token_usage["output_tokens"],
                    },
                )

                return parsed, model_id, token_usage

            except (ClientError, BotoCoreError) as e:
                logger.warning(f"Model {model_id} failed with AWS error: {e}. Trying fallback.")
                last_error = e
                continue
            except ValueError as e:
                logger.warning(f"Model {model_id} returned unparseable response: {e}. Trying fallback.")
                last_error = e
                continue

        # All models failed — wrap in BedrockError and log (Requirement 12.5)
        bedrock_error = BedrockError(
            message=(
                "All Bedrock models are currently unavailable. "
                "Please try again later or check your AWS credentials and region settings."
            ),
            technical_details=f"Last error: {last_error}",
            suggested_actions=[
                "Verify your AWS credentials are configured correctly.",
                "Check that Bedrock is available in your AWS region.",
                "Try again in a few moments — the service may be temporarily throttled.",
                "Consider rephrasing your request to reduce token usage.",
            ],
        )
        if self.audit_logger is not None:
            self.audit_logger.log_error(
                bedrock_error,
                {
                    "operation": "_call_bedrock_with_fallback",
                    "models_tried": models_to_try,
                    "last_error": str(last_error),
                },
                error_code="BEDROCK_ERROR",
            )
        logger.error(
            "All Bedrock models failed. Last error: %s. "
            "Ensure AWS credentials are configured and Bedrock models are accessible.",
            last_error,
        )
        raise bedrock_error from last_error

    def extract_resource_type(self, user_input: str) -> Optional[ResourceType]:
        """
        Identify the AWS resource type from natural language text.

        Uses Bedrock to parse the user input and extract the resource type.
        This is a convenience method that calls parse() internally.

        Args:
            user_input: Natural language description of the infrastructure request.

        Returns:
            ResourceType enum value if identified, None if ambiguous or unrecognized.
        """
        messages = self._build_messages(user_input)
        try:
            parsed, _, _ = self._call_bedrock_with_fallback(messages)
            resource_type_str = parsed.get("resource_type")
            if resource_type_str is None:
                return None
            return ResourceType(resource_type_str)
        except (ValueError, KeyError):
            return None

    def extract_parameters(
        self, user_input: str, resource_type: ResourceType
    ) -> Dict[str, Any]:
        """
        Extract configuration parameters from natural language text.

        Uses Bedrock to parse the user input and extract relevant parameters
        for the specified resource type.

        Args:
            user_input: Natural language description of the infrastructure request.
            resource_type: The identified AWS resource type (used for context).

        Returns:
            Dictionary of extracted parameter key-value pairs.
        """
        # Augment the input with resource type context for better extraction
        augmented_input = (
            f"{user_input}\n[Context: Extracting parameters for {resource_type.value}]"
        )
        messages = self._build_messages(augmented_input)
        try:
            parsed, _, _ = self._call_bedrock_with_fallback(messages)
            return parsed.get("parameters", {})
        except (ValueError, KeyError, RuntimeError):
            return {}

    def extract_environment(self, user_input: str) -> Optional[Environment]:
        """
        Identify the target deployment environment from natural language text.

        Uses Bedrock to parse the user input and extract the environment.

        Args:
            user_input: Natural language description of the infrastructure request.

        Returns:
            Environment enum value if identified, None if not specified or ambiguous.
        """
        messages = self._build_messages(user_input)
        try:
            parsed, _, _ = self._call_bedrock_with_fallback(messages)
            environment_str = parsed.get("environment")
            if environment_str is None:
                return None
            return Environment(environment_str)
        except (ValueError, KeyError):
            return None

    def needs_clarification(self, parsed_result: StructuredRequest) -> Optional[str]:
        """
        Determine if clarification is needed for the parsed request.

        Returns a clarification question when the request is ambiguous or
        missing required information.

        Args:
            parsed_result: The structured request to evaluate.

        Returns:
            A clarification question string if needed, None if the request is clear.
        """
        # Check for missing resource type (Requirement 1.4)
        if parsed_result.resource_type is None:
            return (
                "No pude identificar el tipo de recurso AWS que necesitas. "
                "¿Podrías especificar qué tipo de recurso quieres crear? "
                "Por ejemplo: bucket S3, instancia EC2, base de datos RDS, función Lambda, etc."
            )

        # Check for missing environment (Requirement 1.4)
        if parsed_result.environment is None:
            return (
                "¿En qué ambiente debe desplegarse este recurso? "
                "Por favor especifica: desarrollo (dev), staging, o producción (prod)."
            )

        # Check for low confidence (Requirement 1.4)
        if parsed_result.confidence < 0.7:
            resource_name = (
                parsed_result.resource_type.value
                if parsed_result.resource_type
                else "recurso"
            )
            env_name = (
                parsed_result.environment.value
                if parsed_result.environment
                else "ambiente"
            )
            return (
                f"No estoy completamente seguro de tu solicitud. "
                f"Entendí que quieres un {resource_name} para {env_name}. "
                f"¿Podrías proporcionar más detalles sobre la configuración que necesitas?"
            )

        return None

    def parse(
        self, user_input: str, context: ConversationContext
    ) -> StructuredRequest:
        """
        Parse natural language input into a structured infrastructure request.

        This is the main entry point for the NaturalLanguageParser. It calls
        Bedrock with the user's input and conversation context, extracts all
        relevant information, and returns a StructuredRequest.

        Model usage is logged for cost auditing (Requirement 2.3).

        Args:
            user_input: The natural language request from the user.
            context: The current conversation context including history.

        Returns:
            StructuredRequest with extracted resource type, parameters,
            environment, confidence score, and metadata.

        Raises:
            BedrockError: If Bedrock is unavailable and all fallback models fail.
            ValidationError: If the user input is empty or invalid.
        """
        if not user_input or not user_input.strip():
            validation_error = ValidationError(
                message="User input cannot be empty. Please provide a description of the infrastructure you need.",
                invalid_parameters=["user_input"],
                suggested_actions=[
                    "Provide a description of the AWS resource you want to create.",
                    "Example: 'Create an S3 bucket for storing logs in development'",
                ],
            )
            if self.audit_logger is not None:
                self.audit_logger.log_error(
                    validation_error,
                    {"operation": "parse", "user_input": repr(user_input)},
                    error_code="INVALID_PARAMS",
                )
            raise validation_error

        try:
            # Build messages including conversation history for context
            messages = self._build_messages_with_context(user_input, context)

            # Call Bedrock with fallback support (Requirement 2.1, 2.2)
            parsed, model_used, token_usage = self._call_bedrock_with_fallback(messages)

            # Extract resource type
            resource_type: Optional[ResourceType] = None
            resource_type_str = parsed.get("resource_type")
            if resource_type_str is not None:
                try:
                    resource_type = ResourceType(resource_type_str)
                except ValueError:
                    logger.warning(f"Unknown resource type from model: {resource_type_str}")

            # Extract environment
            environment: Optional[Environment] = None
            environment_str = parsed.get("environment")
            if environment_str is not None:
                try:
                    environment = Environment(environment_str)
                except ValueError:
                    logger.warning(f"Unknown environment from model: {environment_str}")

            # Extract parameters
            parameters: Dict[str, Any] = parsed.get("parameters", {})
            if not isinstance(parameters, dict):
                parameters = {}

            # Extract confidence
            confidence: float = float(parsed.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0.0, 1.0]

            # Extract user justification
            user_justification: str = parsed.get("user_justification", user_input)

            # Generate unique request ID (Requirement 1.5)
            request_id = str(uuid.uuid4())

            # Log model usage for audit (Requirement 2.3)
            total_tokens = token_usage["input_tokens"] + token_usage["output_tokens"]
            logger.info(
                f"Request parsed using model {model_used}: "
                f"resource={resource_type_str}, env={environment_str}, "
                f"confidence={confidence:.2f}, tokens={total_tokens}",
                extra={
                    "event_type": "request_parsed",
                    "model_used": model_used,
                    "tokens_consumed": total_tokens,
                    "request_id": request_id,
                },
            )

            # Build StructuredRequest - use sentinel values for None fields
            # so the dataclass can be instantiated (needs_clarification handles None checks)
            return StructuredRequest(
                resource_type=resource_type,  # type: ignore[arg-type]
                parameters=parameters,
                environment=environment,  # type: ignore[arg-type]
                confidence=confidence,
                user_justification=user_justification,
                request_id=request_id,
                timestamp=datetime.now(timezone.utc),
                technology_type=TechnologyType.TERRAFORM,  # NLP parser is technology-agnostic; callers may override
            )

        except (BedrockError, ValidationError):
            # Re-raise known errors as-is
            raise
        except Exception as exc:
            # Wrap unexpected errors and log them (Requirement 12.5)
            bedrock_error = BedrockError(
                message=(
                    f"An unexpected error occurred while parsing your request: {exc}. "
                    "Please try again or rephrase your request."
                ),
                technical_details=str(exc),
                suggested_actions=[
                    "Try rephrasing your request.",
                    "Verify your AWS credentials and Bedrock access.",
                ],
            )
            if self.audit_logger is not None:
                self.audit_logger.log_error(
                    bedrock_error,
                    {
                        "operation": "parse",
                        "user_input": user_input[:100],
                        "session_id": context.session_id,
                    },
                    error_code="BEDROCK_ERROR",
                )
            logger.error("Unexpected error in parse(): %s", exc)
            raise bedrock_error from exc

    def _build_messages_with_context(
        self, user_input: str, context: ConversationContext
    ) -> List[Dict[str, Any]]:
        """
        Build messages list incorporating conversation history for context.

        Args:
            user_input: The current user input.
            context: The conversation context with history.

        Returns:
            List of message dictionaries including few-shot examples and history.
        """
        messages: List[Dict[str, Any]] = []

        # Add few-shot examples first
        for example in FEW_SHOT_EXAMPLES:
            messages.append({"role": "user", "content": example["user"]})
            messages.append({"role": "assistant", "content": example["assistant"]})

        # Add relevant conversation history (last 4 turns to keep context manageable)
        recent_history = context.history[-8:] if len(context.history) > 8 else context.history
        for turn in recent_history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        # Add the current user request
        messages.append({"role": "user", "content": user_input})

        return messages
