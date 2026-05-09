"""Golden Modules Inventory component for managing Terraform module catalog."""

from typing import Any, Dict, List, Optional
from pathlib import Path
import logging
import re

from .errors import ModuleNotFoundError, RepositoryError
from .interfaces import IModuleInventory
from .models import (
    ResourceType,
    ModuleSchema,
    ModuleInfo,
    Parameter,
)

logger = logging.getLogger(__name__)


class GoldenModulesInventory(IModuleInventory):
    """
    Manages the catalog of available Golden Modules and their schemas.
    
    This component maintains information about the 12 Golden Modules,
    provides access to module schemas, and suggests alternatives for
    unsupported resource types.
    """
    
    def __init__(self, modules_base_path: Optional[str] = None, audit_logger: Optional[Any] = None):
        """
        Initialize the Golden Modules Inventory.
        
        Args:
            modules_base_path: Base path to the Golden Modules directory.
                             If None, uses a default catalog without file system access.
            audit_logger: Optional AuditLogger instance for structured error logging.
        """
        self.modules_base_path = Path(modules_base_path) if modules_base_path else None
        self.audit_logger = audit_logger
        self._module_catalog = self._initialize_catalog()
    
    def _initialize_catalog(self) -> Dict[ResourceType, ModuleInfo]:
        """
        Initialize the catalog of available Golden Modules.
        
        Returns:
            Dictionary mapping ResourceType to ModuleInfo.
        """
        catalog = {
            ResourceType.S3_BUCKET: ModuleInfo(
                resource_type=ResourceType.S3_BUCKET,
                name="S3 Bucket",
                description="Secure S3 bucket with encryption and versioning",
                version="1.0.0"
            ),
            ResourceType.EC2_INSTANCE: ModuleInfo(
                resource_type=ResourceType.EC2_INSTANCE,
                name="EC2 Instance",
                description="EC2 instance with security group and IAM role",
                version="1.0.0"
            ),
            ResourceType.RDS_DATABASE: ModuleInfo(
                resource_type=ResourceType.RDS_DATABASE,
                name="RDS Database",
                description="RDS database with encryption and automated backups",
                version="1.0.0"
            ),
            ResourceType.LAMBDA_FUNCTION: ModuleInfo(
                resource_type=ResourceType.LAMBDA_FUNCTION,
                name="Lambda Function",
                description="Lambda function with IAM role and CloudWatch logging",
                version="1.0.0"
            ),
            ResourceType.API_GATEWAY: ModuleInfo(
                resource_type=ResourceType.API_GATEWAY,
                name="API Gateway",
                description="API Gateway with authentication and throttling",
                version="1.0.0"
            ),
            ResourceType.DYNAMODB_TABLE: ModuleInfo(
                resource_type=ResourceType.DYNAMODB_TABLE,
                name="DynamoDB Table",
                description="DynamoDB table with encryption and point-in-time recovery",
                version="1.0.0"
            ),
            ResourceType.VPC: ModuleInfo(
                resource_type=ResourceType.VPC,
                name="VPC",
                description="VPC with public and private subnets",
                version="1.0.0"
            ),
            ResourceType.SECURITY_GROUP: ModuleInfo(
                resource_type=ResourceType.SECURITY_GROUP,
                name="Security Group",
                description="Security group with restrictive default rules",
                version="1.0.0"
            ),
            ResourceType.IAM_ROLE: ModuleInfo(
                resource_type=ResourceType.IAM_ROLE,
                name="IAM Role",
                description="IAM role with least privilege policies",
                version="1.0.0"
            ),
            ResourceType.CLOUDWATCH_LOG_GROUP: ModuleInfo(
                resource_type=ResourceType.CLOUDWATCH_LOG_GROUP,
                name="CloudWatch Log Group",
                description="CloudWatch log group with retention policies",
                version="1.0.0"
            ),
            ResourceType.SNS_TOPIC: ModuleInfo(
                resource_type=ResourceType.SNS_TOPIC,
                name="SNS Topic",
                description="SNS topic with encryption and access policies",
                version="1.0.0"
            ),
            ResourceType.SQS_QUEUE: ModuleInfo(
                resource_type=ResourceType.SQS_QUEUE,
                name="SQS Queue",
                description="SQS queue with encryption and dead letter queue",
                version="1.0.0"
            ),
        }
        return catalog
    
    def get_module(self, resource_type: ResourceType) -> Optional[ModuleInfo]:
        """
        Retrieve Golden Module information by ResourceType.
        
        Args:
            resource_type: The type of AWS resource.
            
        Returns:
            ModuleInfo if the module exists, None otherwise.
        """
        return self._module_catalog.get(resource_type)
    
    def list_available_modules(self) -> List[ModuleInfo]:
        """
        List all available Golden Modules.
        
        Returns:
            List of ModuleInfo for all 12 Golden Modules.
        """
        return list(self._module_catalog.values())
    
    def get_module_schema(self, resource_type: ResourceType) -> ModuleSchema:
        """
        Extract parameter schema from Golden Module.
        
        This method retrieves the complete schema for a Golden Module,
        including required parameters, optional parameters, and security parameters.
        
        If modules_base_path is provided, it will attempt to parse the variables.tf
        file to extract the actual schema. Otherwise, it returns a predefined schema.
        
        Args:
            resource_type: The type of AWS resource.
            
        Returns:
            ModuleSchema containing parameter definitions.
            
        Raises:
            ModuleNotFoundError: If the resource type is not supported (Req 12.4).
        """
        module_info = self.get_module(resource_type)
        if not module_info:
            not_found_error = ModuleNotFoundError(
                message=(
                    f"Golden Module for '{resource_type.value}' was not found in the inventory. "
                    "Please verify the resource type is supported and the Base_Repository "
                    "is accessible."
                ),
                technical_details=f"resource_type={resource_type.value}",
                suggested_actions=[
                    "Check the list of available Golden Modules using list_available_modules().",
                    "Request a similar supported resource type.",
                    "Verify that the Base_Repository contains the expected module directory.",
                ],
            )
            # Requirement 12.5: log the error for later diagnosis
            if self.audit_logger is not None:
                self.audit_logger.log_error(
                    not_found_error,
                    {"operation": "get_module_schema", "resource_type": resource_type.value},
                    error_code="MODULE_NOT_FOUND",
                )
            logger.error(
                "Module not found for resource type '%s'. "
                "Verify the Base_Repository is accessible and permissions are correct.",
                resource_type.value,
            )
            raise not_found_error
        
        # If we have a base path, try to parse variables.tf
        if self.modules_base_path:
            schema = self._parse_variables_tf(resource_type)
            if schema:
                return schema
        
        # Otherwise, return predefined schemas
        return self._get_predefined_schema(resource_type)
    
    def _parse_variables_tf(self, resource_type: ResourceType) -> Optional[ModuleSchema]:
        """
        Parse variables.tf file to extract parameter schema.
        
        Args:
            resource_type: The type of AWS resource.
            
        Returns:
            ModuleSchema if parsing succeeds, None otherwise.
        """
        if not self.modules_base_path:
            return None
        
        # Construct path to variables.tf
        module_dir = self.modules_base_path / resource_type.value
        variables_file = module_dir / "variables.tf"
        
        if not variables_file.exists():
            # Requirement 12.4: inform user when Base_Repository is not accessible
            repo_error = RepositoryError(
                message=(
                    f"Module directory for '{resource_type.value}' not found at "
                    f"'{module_dir}'. Please verify the Base_Repository is accessible "
                    "and you have the required permissions."
                ),
                technical_details=f"Expected path: {variables_file}",
                suggested_actions=[
                    "Verify that the Base_Repository has been cloned correctly.",
                    f"Check that the '{resource_type.value}' module directory exists.",
                    "Ensure you have read permissions on the repository.",
                ],
            )
            # Requirement 12.5: log the error for later diagnosis
            if self.audit_logger is not None:
                self.audit_logger.log_error(
                    repo_error,
                    {
                        "operation": "_parse_variables_tf",
                        "resource_type": resource_type.value,
                        "expected_path": str(variables_file),
                    },
                    error_code="REPO_ERROR",
                )
            logger.warning(
                "variables.tf not found for module '%s' at '%s'. "
                "Falling back to predefined schema. "
                "Verify the Base_Repository is accessible and permissions are correct.",
                resource_type.value,
                variables_file,
            )
            return None
        
        try:
            content = variables_file.read_text()
            return self._extract_schema_from_tf(content, resource_type)
        except PermissionError as exc:
            # Requirement 12.4: inform user about permission issues
            repo_error = RepositoryError(
                message=(
                    f"Permission denied reading '{variables_file}'. "
                    "Please verify you have read access to the Base_Repository."
                ),
                technical_details=str(exc),
                suggested_actions=[
                    "Verify that you have read permissions on the repository directory.",
                    "Check file system permissions for the module path.",
                ],
            )
            if self.audit_logger is not None:
                self.audit_logger.log_error(
                    repo_error,
                    {
                        "operation": "_parse_variables_tf",
                        "resource_type": resource_type.value,
                        "file_path": str(variables_file),
                    },
                    error_code="REPO_ERROR",
                )
            logger.warning(
                "Permission denied reading variables.tf for '%s': %s. "
                "Falling back to predefined schema.",
                resource_type.value,
                exc,
            )
            return None
        except Exception as exc:
            # Requirement 12.5: log unexpected errors for later diagnosis
            logger.warning(
                "Failed to parse variables.tf for '%s': %s. "
                "Falling back to predefined schema.",
                resource_type.value,
                exc,
            )
            if self.audit_logger is not None:
                self.audit_logger.log_error(
                    exc,
                    {
                        "operation": "_parse_variables_tf",
                        "resource_type": resource_type.value,
                        "file_path": str(variables_file),
                    },
                    error_code="PARSE_ERROR",
                )
            # If parsing fails, fall back to predefined schema
            return None
    
    def _extract_schema_from_tf(self, content: str, resource_type: ResourceType) -> ModuleSchema:
        """
        Extract schema from Terraform variables.tf content.
        
        This is a simplified parser that extracts variable blocks.
        A production implementation would use a proper HCL parser.
        
        Args:
            content: Content of variables.tf file.
            resource_type: The type of AWS resource.
            
        Returns:
            ModuleSchema extracted from the file.
        """
        # Simple regex-based extraction (production would use HCL parser)
        variable_pattern = r'variable\s+"([^"]+)"\s*\{([^}]+)\}'
        variables = re.findall(variable_pattern, content, re.DOTALL)
        
        required_params = []
        optional_params = []
        security_params = []
        
        for var_name, var_body in variables:
            param = self._parse_variable_block(var_name, var_body)
            
            # Categorize parameters
            if param.is_security_parameter:
                security_params.append(param)
            elif param.required:
                required_params.append(param)
            else:
                optional_params.append(param)
        
        module_info = self.get_module(resource_type)
        module_path = f"modules/{resource_type.value}"
        
        return ModuleSchema(
            resource_type=resource_type,
            module_path=module_path,
            required_parameters=required_params,
            optional_parameters=optional_params,
            security_parameters=security_params,
            naming_pattern="{project}-{env}-{resource}-{suffix}",
            description=module_info.description if module_info else "",
            version=module_info.version if module_info else "1.0.0"
        )
    
    def _parse_variable_block(self, name: str, body: str) -> Parameter:
        """
        Parse a single variable block from Terraform.
        
        Args:
            name: Variable name.
            body: Variable block body.
            
        Returns:
            Parameter object.
        """
        # Extract type
        type_match = re.search(r'type\s*=\s*(\w+)', body)
        param_type = type_match.group(1) if type_match else "string"
        
        # Extract description
        desc_match = re.search(r'description\s*=\s*"([^"]+)"', body)
        description = desc_match.group(1) if desc_match else ""
        
        # Extract default value
        default_match = re.search(r'default\s*=\s*([^\n]+)', body)
        has_default = default_match is not None
        default_value = default_match.group(1).strip() if has_default else None
        
        # Determine if required (no default value)
        required = not has_default
        
        # Determine if security parameter (heuristic based on name)
        security_keywords = ['encryption', 'security', 'kms', 'ssl', 'tls', 'auth', 'versioning']
        is_security = any(keyword in name.lower() for keyword in security_keywords)
        
        return Parameter(
            name=name,
            type=param_type,
            required=required,
            default=default_value,
            description=description,
            validation_rules=None,
            is_security_parameter=is_security
        )
    
    def _get_predefined_schema(self, resource_type: ResourceType) -> ModuleSchema:
        """
        Get predefined schema for a resource type.
        
        This provides default schemas when variables.tf parsing is not available.
        
        Args:
            resource_type: The type of AWS resource.
            
        Returns:
            ModuleSchema with predefined parameters.
        """
        schemas = {
            ResourceType.S3_BUCKET: ModuleSchema(
                resource_type=ResourceType.S3_BUCKET,
                module_path="modules/s3_bucket",
                required_parameters=[
                    Parameter(
                        name="bucket_name",
                        type="string",
                        required=True,
                        default=None,
                        description="Name of the S3 bucket",
                        is_security_parameter=False
                    ),
                    Parameter(
                        name="environment",
                        type="string",
                        required=True,
                        default=None,
                        description="Deployment environment",
                        is_security_parameter=False
                    ),
                ],
                optional_parameters=[
                    Parameter(
                        name="tags",
                        type="map",
                        required=False,
                        default="{}",
                        description="Additional tags for the bucket",
                        is_security_parameter=False
                    ),
                ],
                security_parameters=[
                    Parameter(
                        name="encryption_enabled",
                        type="bool",
                        required=True,
                        default="true",
                        description="Enable server-side encryption",
                        is_security_parameter=True
                    ),
                    Parameter(
                        name="versioning_enabled",
                        type="bool",
                        required=True,
                        default="true",
                        description="Enable versioning",
                        is_security_parameter=True
                    ),
                ],
                naming_pattern="{project}-{env}-{bucket_name}",
                description="Secure S3 bucket with encryption and versioning",
                version="1.0.0"
            ),
            ResourceType.EC2_INSTANCE: ModuleSchema(
                resource_type=ResourceType.EC2_INSTANCE,
                module_path="modules/ec2_instance",
                required_parameters=[
                    Parameter(
                        name="instance_name",
                        type="string",
                        required=True,
                        default=None,
                        description="Name of the EC2 instance",
                        is_security_parameter=False
                    ),
                    Parameter(
                        name="instance_type",
                        type="string",
                        required=True,
                        default=None,
                        description="EC2 instance type (e.g., t3.micro)",
                        is_security_parameter=False
                    ),
                    Parameter(
                        name="environment",
                        type="string",
                        required=True,
                        default=None,
                        description="Deployment environment",
                        is_security_parameter=False
                    ),
                ],
                optional_parameters=[
                    Parameter(
                        name="ami_id",
                        type="string",
                        required=False,
                        default="latest-amazon-linux-2",
                        description="AMI ID for the instance",
                        is_security_parameter=False
                    ),
                ],
                security_parameters=[
                    Parameter(
                        name="enable_detailed_monitoring",
                        type="bool",
                        required=True,
                        default="true",
                        description="Enable detailed CloudWatch monitoring",
                        is_security_parameter=True
                    ),
                ],
                naming_pattern="{project}-{env}-{instance_name}",
                description="EC2 instance with security group and IAM role",
                version="1.0.0"
            ),
            ResourceType.RDS_DATABASE: ModuleSchema(
                resource_type=ResourceType.RDS_DATABASE,
                module_path="modules/rds_database",
                required_parameters=[
                    Parameter(
                        name="db_name",
                        type="string",
                        required=True,
                        default=None,
                        description="Database name",
                        is_security_parameter=False
                    ),
                    Parameter(
                        name="engine",
                        type="string",
                        required=True,
                        default=None,
                        description="Database engine (postgres, mysql, etc.)",
                        is_security_parameter=False
                    ),
                    Parameter(
                        name="environment",
                        type="string",
                        required=True,
                        default=None,
                        description="Deployment environment",
                        is_security_parameter=False
                    ),
                ],
                optional_parameters=[
                    Parameter(
                        name="instance_class",
                        type="string",
                        required=False,
                        default="db.t3.micro",
                        description="RDS instance class",
                        is_security_parameter=False
                    ),
                ],
                security_parameters=[
                    Parameter(
                        name="storage_encrypted",
                        type="bool",
                        required=True,
                        default="true",
                        description="Enable storage encryption",
                        is_security_parameter=True
                    ),
                    Parameter(
                        name="backup_retention_period",
                        type="number",
                        required=True,
                        default="7",
                        description="Backup retention period in days",
                        is_security_parameter=True
                    ),
                ],
                naming_pattern="{project}-{env}-{db_name}",
                description="RDS database with encryption and automated backups",
                version="1.0.0"
            ),
            ResourceType.LAMBDA_FUNCTION: ModuleSchema(
                resource_type=ResourceType.LAMBDA_FUNCTION,
                module_path="modules/lambda_function",
                required_parameters=[
                    Parameter(
                        name="function_name",
                        type="string",
                        required=True,
                        default=None,
                        description="Name of the Lambda function",
                        is_security_parameter=False
                    ),
                    Parameter(
                        name="runtime",
                        type="string",
                        required=True,
                        default=None,
                        description="Lambda runtime (python3.11, nodejs18.x, etc.)",
                        is_security_parameter=False
                    ),
                    Parameter(
                        name="environment",
                        type="string",
                        required=True,
                        default=None,
                        description="Deployment environment",
                        is_security_parameter=False
                    ),
                ],
                optional_parameters=[
                    Parameter(
                        name="memory_size",
                        type="number",
                        required=False,
                        default="128",
                        description="Memory size in MB",
                        is_security_parameter=False
                    ),
                    Parameter(
                        name="timeout",
                        type="number",
                        required=False,
                        default="30",
                        description="Timeout in seconds",
                        is_security_parameter=False
                    ),
                ],
                security_parameters=[
                    Parameter(
                        name="enable_cloudwatch_logs",
                        type="bool",
                        required=True,
                        default="true",
                        description="Enable CloudWatch logging",
                        is_security_parameter=True
                    ),
                ],
                naming_pattern="{project}-{env}-{function_name}",
                description="Lambda function with IAM role and CloudWatch logging",
                version="1.0.0"
            ),
        }
        
        # For resource types not explicitly defined, create a minimal schema
        if resource_type not in schemas:
            module_info = self.get_module(resource_type)
            return ModuleSchema(
                resource_type=resource_type,
                module_path=f"modules/{resource_type.value}",
                required_parameters=[
                    Parameter(
                        name="name",
                        type="string",
                        required=True,
                        default=None,
                        description=f"Name of the {resource_type.value}",
                        is_security_parameter=False
                    ),
                    Parameter(
                        name="environment",
                        type="string",
                        required=True,
                        default=None,
                        description="Deployment environment",
                        is_security_parameter=False
                    ),
                ],
                optional_parameters=[],
                security_parameters=[],
                naming_pattern="{project}-{env}-{name}",
                description=module_info.description if module_info else f"{resource_type.value} module",
                version="1.0.0"
            )
        
        return schemas[resource_type]
    
    def suggest_alternatives(self, resource_type: ResourceType) -> List[ResourceType]:
        """
        Suggest alternative resource types for unsupported requests.
        
        This method provides intelligent suggestions based on resource type similarity.
        
        Args:
            resource_type: The requested resource type.
            
        Returns:
            List of alternative ResourceType suggestions.
        """
        # If the resource type is supported, return empty list
        if self.get_module(resource_type):
            return []
        
        # Define similarity groups
        storage_resources = [ResourceType.S3_BUCKET, ResourceType.DYNAMODB_TABLE]
        compute_resources = [ResourceType.EC2_INSTANCE, ResourceType.LAMBDA_FUNCTION]
        database_resources = [ResourceType.RDS_DATABASE, ResourceType.DYNAMODB_TABLE]
        networking_resources = [ResourceType.VPC, ResourceType.SECURITY_GROUP, ResourceType.API_GATEWAY]
        messaging_resources = [ResourceType.SNS_TOPIC, ResourceType.SQS_QUEUE]
        monitoring_resources = [ResourceType.CLOUDWATCH_LOG_GROUP]
        security_resources = [ResourceType.IAM_ROLE, ResourceType.SECURITY_GROUP]
        
        # Map resource types to their similarity groups
        similarity_map = {}
        for resource in storage_resources:
            similarity_map[resource] = storage_resources
        for resource in compute_resources:
            similarity_map[resource] = compute_resources
        for resource in database_resources:
            similarity_map[resource] = database_resources
        for resource in networking_resources:
            similarity_map[resource] = networking_resources
        for resource in messaging_resources:
            similarity_map[resource] = messaging_resources
        for resource in monitoring_resources:
            similarity_map[resource] = monitoring_resources
        for resource in security_resources:
            similarity_map[resource] = security_resources
        
        # Get alternatives from the same group
        alternatives = similarity_map.get(resource_type, [])
        
        # Remove the requested resource type from alternatives
        alternatives = [alt for alt in alternatives if alt != resource_type]
        
        # If no alternatives found, return a few popular options
        if not alternatives:
            alternatives = [
                ResourceType.S3_BUCKET,
                ResourceType.LAMBDA_FUNCTION,
                ResourceType.RDS_DATABASE,
            ]
        
        return alternatives
