# Bedrock IaC Agent

A conversational AI agent for AWS infrastructure deployment using AWS Bedrock and Terraform.

## Overview

The Bedrock IaC Agent lets developers describe the AWS infrastructure they need in plain language. The agent interprets the request, generates a Terraform tfvars file using a pre-built Golden Module, and opens a Pull Request in your GitHub repository for review and deployment — all without writing a single line of Terraform.

```
You> I need an S3 bucket for storing logs in development

Agent> ✅ Pull Request created successfully!

Resource: s3_bucket
Environment: dev
PR URL: https://github.com/my-org/my-infra-repo/pull/42
```

## Features

- **Natural language interface** — describe infrastructure in plain English (or Spanish)
- **Terraform tfvars generation** — produces valid HCL files from Golden Module schemas
- **GitHub automation** — clones the repo, creates a branch, commits, and opens a PR
- **Security by default** — Golden Modules enforce encryption, versioning, and least-privilege settings that cannot be overridden
- **Cost-optimised AI** — uses economic AWS Bedrock models (Nova Micro as default)
- **Audit logging** — every request, configuration, and PR is logged in structured JSON
- **Conversational context** — maintains session state across multiple turns
- **12 Golden Modules** — covers the most common AWS resource types out of the box

## Requirements

- Python 3.9 or higher
- AWS account with Bedrock access (Amazon Nova Micro or another supported model enabled in your region)
- GitHub personal access token with `repo` and `pull_request` scopes
- AWS credentials configured (via `~/.aws/credentials`, environment variables, or an IAM role)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/my-org/bedrock-iac-agent.git
cd bedrock-iac-agent
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
```

### 3. Install the package

```bash
# Runtime only
pip install -e .

# With development tools (pytest, black, ruff, mypy)
pip install -e ".[dev]"
```

The `bedrock-iac-agent` CLI command is now available in your shell.

## Configuration

### config.yaml

Copy the example file and fill in your values:

```bash
cp config.yaml.example config.yaml
```

The agent searches for `config.yaml` in the current working directory first, then in `~/.bedrock-iac-agent/config.yaml`.

```yaml
# GitHub credentials and repository settings
github:
  token: ""                          # Personal access token (prefer GITHUB_TOKEN env var)
  organization: "my-org"             # GitHub organisation that owns the repository
  repository: "my-infra-repo"        # Repository name (without the org prefix)
  repo_url: "https://github.com/my-org/my-infra-repo.git"  # Optional — derived if omitted

# AWS Bedrock model and region settings
bedrock:
  model_id: "amazon.nova-micro-v1:0"  # Default model (most cost-efficient)
  region: "us-east-1"
  aws_profile: null                  # Optional named profile from ~/.aws/config

# Naming conventions for generated resources
naming:
  prefix: ""                         # Optional prefix for all resource names
  environment_suffix: true           # Append environment name (e.g. "bucket-dev")
  separator: "-"
  max_length: 63
  allowed_characters: "[a-z0-9\\-]"
```

### Environment variables

Sensitive credentials should be set via environment variables rather than stored in `config.yaml`. Environment variables take the highest priority and override file-based values.

| Environment variable  | Config key              | Description                                      |
|-----------------------|-------------------------|--------------------------------------------------|
| `GITHUB_TOKEN`        | `github.token`          | GitHub personal access token                     |
| `GITHUB_ORG`          | `github.organization`   | GitHub organisation name                         |
| `GITHUB_REPO`         | `github.repository`     | Repository name                                  |
| `GITHUB_REPO_URL`     | `github.repo_url`       | Full HTTPS clone URL (optional)                  |
| `BEDROCK_MODEL_ID`    | `bedrock.model_id`      | Bedrock model ID                                 |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | `bedrock.region` | AWS region                          |
| `AWS_PROFILE`         | `bedrock.aws_profile`   | Named AWS profile                                |

Quick setup example:

```bash
export GITHUB_TOKEN="ghp_your_token_here"
export GITHUB_ORG="my-org"
export GITHUB_REPO="my-infra-repo"
export AWS_DEFAULT_REGION="us-east-1"
```

### AWS credentials

The agent uses the standard AWS credential chain. Any of the following work:

```bash
# Option 1: Environment variables
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."

# Option 2: Named profile in ~/.aws/config
export AWS_PROFILE="my-dev-profile"

# Option 3: IAM role (EC2 instance profile, ECS task role, etc.)
# No additional configuration needed
```

Make sure the Bedrock model you want to use is enabled in the AWS console under **Amazon Bedrock → Model access** for your region.

## Usage

### Start an interactive session

```bash
bedrock-iac-agent
# or explicitly:
bedrock-iac-agent chat
```

Pass credentials directly on the command line (they override config.yaml and env vars):

```bash
bedrock-iac-agent chat \
  --github-token ghp_... \
  --github-org my-org \
  --github-repo my-infra-repo \
  --aws-region us-east-1
```

Point to a specific config file:

```bash
bedrock-iac-agent chat --config /path/to/config.yaml
```

### List available resource types

```bash
bedrock-iac-agent list-resources
```

### CLI options reference

```
bedrock-iac-agent chat [OPTIONS]

Options:
  --user-id TEXT          User identifier for audit logging  [default: cli-user]
  --session-id TEXT       Session identifier (auto-generated if omitted)
  --config PATH           Path to config.yaml  [env: BEDROCK_IAC_CONFIG]
  --github-token TEXT     GitHub personal access token  [env: GITHUB_TOKEN]
  --github-org TEXT       GitHub organisation name  [env: GITHUB_ORG]
  --github-repo TEXT      GitHub repository name  [env: GITHUB_REPO]
  --github-repo-url TEXT  Full HTTPS URL of the repository  [env: GITHUB_REPO_URL]
  --bedrock-model-id TEXT AWS Bedrock model ID  [env: BEDROCK_MODEL_ID]
  --aws-region TEXT       AWS region  [env: AWS_DEFAULT_REGION]
  --aws-profile TEXT      AWS named profile  [env: AWS_PROFILE]
```

### Session commands

Once inside the interactive session:

| Command              | Description                                      |
|----------------------|--------------------------------------------------|
| `help` or `?`        | Show available commands                          |
| `resources` or `list`| List all 12 supported Golden Module types        |
| `exit`, `quit`, `q`  | Exit the session cleanly                         |
| Any other text       | Send a natural language infrastructure request   |

## Usage examples

### S3 Bucket

```
You> Create an S3 bucket called data-lake for the development environment
You> I need a bucket to store application logs in production
You> Set up an S3 bucket named backups in staging
```

### EC2 Instance

```
You> I need a t3.micro EC2 instance for the dev environment
You> Provision an EC2 instance called web-server with instance type t3.small in production
You> Create a small EC2 instance for running batch jobs in staging
```

### RDS Database

```
You> Create a PostgreSQL RDS database called users-db in development
You> I need a MySQL database for the production environment, db.t3.small instance class
You> Set up an RDS database named analytics in staging
```

### Lambda Function

```
You> Create a Lambda function called image-processor using Python 3.11 in dev
You> I need a Node.js Lambda function for the production environment with 512 MB memory
You> Set up a Lambda function named data-transformer with a 60-second timeout in staging
```

### API Gateway

```
You> Create an API Gateway for the user-service in development
You> I need an API Gateway called payments-api in production
You> Set up an API Gateway for the notification service in staging
```

### DynamoDB Table

```
You> Create a DynamoDB table called sessions in development
You> I need a DynamoDB table for storing user preferences in production
You> Set up a DynamoDB table named events in staging
```

### VPC

```
You> Create a VPC for the development environment
You> I need a VPC with public and private subnets in production
You> Set up a VPC called app-network in staging
```

### Security Group

```
You> Create a security group for the web tier in development
You> I need a security group called db-access in production
You> Set up a security group for the application servers in staging
```

### IAM Role

```
You> Create an IAM role for Lambda execution in development
You> I need an IAM role called ec2-s3-access in production
You> Set up an IAM role for the ECS task in staging
```

### CloudWatch Log Group

```
You> Create a CloudWatch log group for the API service in development
You> I need a log group called /app/payments in production with 30-day retention
You> Set up a CloudWatch log group for Lambda logs in staging
```

### SNS Topic

```
You> Create an SNS topic for order notifications in development
You> I need an SNS topic called alerts in production
You> Set up an SNS topic for deployment events in staging
```

### SQS Queue

```
You> Create an SQS queue for processing image uploads in development
You> I need a queue called payment-events in production
You> Set up an SQS queue with a dead letter queue for the order service in staging
```

## Supported Golden Modules

The agent supports exactly 12 AWS resource types. Each Golden Module is a pre-built Terraform module that enforces security best practices and cannot be modified by the agent — only the tfvars parameters are generated.

| # | Resource Type           | Module Key               | Description                                                  |
|---|-------------------------|--------------------------|--------------------------------------------------------------|
| 1 | S3 Bucket               | `s3_bucket`              | Secure S3 bucket with encryption and versioning              |
| 2 | EC2 Instance            | `ec2_instance`           | EC2 instance with security group and IAM role                |
| 3 | RDS Database            | `rds_database`           | RDS database with encryption and automated backups           |
| 4 | Lambda Function         | `lambda_function`        | Lambda function with IAM role and CloudWatch logging         |
| 5 | API Gateway             | `api_gateway`            | API Gateway with authentication and throttling               |
| 6 | DynamoDB Table          | `dynamodb_table`         | DynamoDB table with encryption and point-in-time recovery    |
| 7 | VPC                     | `vpc`                    | VPC with public and private subnets                          |
| 8 | Security Group          | `security_group`         | Security group with restrictive default rules                |
| 9 | IAM Role                | `iam_role`               | IAM role with least-privilege policies                       |
|10 | CloudWatch Log Group    | `cloudwatch_log_group`   | CloudWatch log group with retention policies                 |
|11 | SNS Topic               | `sns_topic`              | SNS topic with encryption and access policies                |
|12 | SQS Queue               | `sqs_queue`              | SQS queue with encryption and dead letter queue              |

### Security parameters

Each Golden Module enforces security parameters that the agent will never override, regardless of what the user requests:

- **S3 Bucket**: `encryption_enabled`, `versioning_enabled`
- **RDS Database**: `storage_encrypted`, `backup_retention_period`
- **EC2 Instance**: `enable_detailed_monitoring`
- **Lambda Function**: `enable_cloudwatch_logs`
- **DynamoDB Table**: encryption at rest, point-in-time recovery
- **SQS Queue**: server-side encryption, dead letter queue configuration

If you request a resource type not in this list, the agent will inform you and suggest the closest available alternative.

## Architecture

```
User (CLI)
    │
    ▼
CLIInterface          ← Click-based REPL with Rich formatting
    │
    ▼
BedrockIaCAgent       ← Orchestrator: wires all components together
    ├── NaturalLanguageParser    ← Calls AWS Bedrock to parse requests
    ├── GoldenModulesInventory   ← Catalog of 12 module schemas
    ├── ConfigurationGenerator   ← Generates HCL tfvars files
    ├── GitHubIntegration        ← Clones repo, commits, creates PR
    └── AuditLogger              ← Structured JSON logging
```

The agent only ever writes `.tfvars` files. Terraform module code (`.tf` files) and Golden Modules are never modified.

## Development

### Running tests

```bash
# All tests
pytest

# With coverage report
pytest --cov --cov-report=html
open htmlcov/index.html

# Skip integration tests that call real AWS APIs
pytest -m "not integration"

# Specific test file
pytest tests/test_agent.py -v
```

### Code quality

```bash
# Format
black src/ tests/

# Lint
ruff check src/ tests/
ruff check --fix src/ tests/

# Type check
mypy src/
```

### Supported Bedrock models

The default model is `amazon.nova-micro-v1:0` — Amazon's most economical option. Alternatives:

| Model ID                                  | Notes                        |
|-------------------------------------------|------------------------------|
| `amazon.nova-micro-v1:0`                  | Default — most cost-efficient|
| `amazon.nova-lite-v1:0`                   | Slightly more capable        |
| `anthropic.claude-3-haiku-20240307-v1:0`  | Alternative — requires model access request in AWS console |

Set the model via `config.yaml` or the `BEDROCK_MODEL_ID` environment variable.

## Troubleshooting

**`No agent configured` warning at startup**
The agent starts in a limited mode when GitHub or Bedrock credentials are missing. Set the required environment variables (`GITHUB_TOKEN`, `GITHUB_ORG`, `GITHUB_REPO`, `AWS_DEFAULT_REGION`) and restart.

**`GitHub integration requires github.token, github.organization, and github.repository`**
All three GitHub fields must be set. Partial credentials disable GitHub operations.

**Bedrock `AccessDeniedException`**
The model you selected may not be enabled in your AWS account. Go to **Amazon Bedrock → Model access** in the AWS console and enable the model for your region.

**`variables.tf not found` warning**
The agent falls back to predefined schemas when the Golden Modules directory is not present locally. This is expected when running without a cloned base repository — the agent will still generate valid tfvars using built-in schemas.

**Virtual environment issues**
```bash
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

## Contributing

1. Fork the repository and create a feature branch
2. Install dev dependencies: `pip install -e ".[dev]"`
3. Make your changes
4. Run tests: `pytest -m "not integration"`
5. Run code quality checks: `black src/ tests/ && ruff check src/ tests/ && mypy src/`
6. Open a Pull Request

## License

MIT License — see [LICENSE](LICENSE) for details.
