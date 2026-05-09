# Troubleshooting Guide

This guide covers the most common issues encountered when running the Bedrock IaC Agent, along with their causes and solutions.

---

## Table of Contents

1. [Authentication errors](#1-authentication-errors)
   - [GitHub token errors](#11-github-token-errors)
   - [AWS / Bedrock access errors](#12-aws--bedrock-access-errors)
2. [Configuration errors](#2-configuration-errors)
3. [Network errors](#3-network-errors)
4. [Unsupported resource types](#4-unsupported-resource-types)
5. [Tfvars generation errors](#5-tfvars-generation-errors)
6. [GitHub repository errors](#6-github-repository-errors)
7. [CLI and startup issues](#7-cli-and-startup-issues)
8. [Bedrock model errors](#8-bedrock-model-errors)
9. [Audit logging issues](#9-audit-logging-issues)
10. [Installation and environment issues](#10-installation-and-environment-issues)

---

## 1. Authentication errors

### 1.1 GitHub token errors

#### Symptom: `GitHub integration requires github.token, github.organization, and github.repository`

**Cause**: One or more of the three required GitHub fields is missing.

**Solution**: All three must be set together. Use environment variables:

```bash
export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export GITHUB_ORG="my-org"
export GITHUB_REPO="my-infra-repo"
```

Or set them in `config.yaml`:

```yaml
github:
  token: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  organization: "my-org"
  repository: "my-infra-repo"
```

---

#### Symptom: `401 Unauthorized` or `Bad credentials` from GitHub API

**Cause**: The GitHub personal access token is invalid, expired, or has insufficient scopes.

**Solution**:
1. Generate a new token at <https://github.com/settings/tokens>
2. Select the following scopes:
   - `repo` — full control of private repositories
   - `pull_request` — create and manage pull requests (included in `repo`)
3. Update `GITHUB_TOKEN` with the new token
4. Verify the token works:
   ```bash
   curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
   ```

---

#### Symptom: `403 Forbidden` when creating a Pull Request

**Cause**: The token has `repo` scope but the account does not have write access to the repository, or the repository requires organisation-level SSO authorisation.

**Solution**:
1. Confirm the token owner has at least `Write` access to the repository
2. If the organisation enforces SAML SSO, authorise the token:
   - Go to <https://github.com/settings/tokens>
   - Click **Configure SSO** next to the token
   - Authorise the organisation

---

### 1.2 AWS / Bedrock access errors

#### Symptom: `AccessDeniedException` when calling Bedrock

**Cause**: The Bedrock model is not enabled in your AWS account, or the IAM principal lacks `bedrock:InvokeModel` permission.

**Solution**:
1. Enable the model in the AWS console:
   - Navigate to **Amazon Bedrock → Model access**
   - Select your region
   - Enable `anthropic.claude-3-haiku-20240307-v1:0` (or your chosen model)
2. Verify the IAM policy attached to your credentials includes:
   ```json
   {
     "Effect": "Allow",
     "Action": ["bedrock:InvokeModel"],
     "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
   }
   ```

---

#### Symptom: `NoCredentialsError` or `Unable to locate credentials`

**Cause**: No AWS credentials are configured.

**Solution**: Configure credentials using one of these methods:

```bash
# Option 1: Environment variables
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="us-east-1"

# Option 2: Named profile
export AWS_PROFILE="my-dev-profile"

# Option 3: AWS CLI configuration
aws configure
```

Verify credentials are working:

```bash
aws sts get-caller-identity
```

---

#### Symptom: `ExpiredTokenException`

**Cause**: Temporary credentials (from STS, SSO, or an assumed role) have expired.

**Solution**: Refresh your credentials:

```bash
# For AWS SSO
aws sso login --profile my-profile

# For assumed roles, re-run the assume-role command
aws sts assume-role --role-arn arn:aws:iam::123456789012:role/MyRole --role-session-name session
```

---

## 2. Configuration errors

#### Symptom: `No agent configured` warning at startup

**Cause**: The agent starts in limited mode when GitHub or Bedrock credentials are missing. Natural language requests will fail, but the `resources` / `list` command still works.

**Solution**: Set the minimum required environment variables and restart:

```bash
export GITHUB_TOKEN="ghp_..."
export GITHUB_ORG="my-org"
export GITHUB_REPO="my-infra-repo"
export AWS_DEFAULT_REGION="us-east-1"
bedrock-iac-agent chat
```

---

#### Symptom: `Failed to parse config file config.yaml`

**Cause**: The YAML file contains a syntax error.

**Solution**: Validate the YAML syntax:

```bash
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

Common YAML mistakes:
- Tabs instead of spaces for indentation
- Missing quotes around values that contain special characters (`:`, `#`, `{`, `}`)
- Incorrect indentation level

---

#### Symptom: `bedrock.model_id must not be empty`

**Cause**: The `model_id` field was explicitly set to an empty string in `config.yaml`.

**Solution**: Either remove the `model_id` line (the default will be used) or set a valid model ID:

```yaml
bedrock:
  model_id: "anthropic.claude-3-haiku-20240307-v1:0"
```

---

#### Symptom: `naming.max_length must be a positive integer`

**Cause**: `max_length` was set to `0` or a negative number.

**Solution**: Set a positive value. The recommended default is `63`:

```yaml
naming:
  max_length: 63
```

---

## 3. Network errors

#### Symptom: `ConnectionError` or `ReadTimeout` during GitHub operations

**Cause**: Network connectivity issue between the agent and GitHub API.

**Solution**:
1. The agent automatically retries up to 3 times with exponential backoff
2. If all retries fail, check your network connection:
   ```bash
   curl -I https://api.github.com
   ```
3. If you are behind a corporate proxy, set the proxy environment variables:
   ```bash
   export HTTPS_PROXY="https://proxy.mycompany.com:8080"
   export HTTP_PROXY="http://proxy.mycompany.com:8080"
   ```

---

#### Symptom: `SSLError` or `certificate verify failed`

**Cause**: SSL certificate verification failure, common in corporate environments with TLS inspection.

**Solution**:
1. If your organisation uses a custom CA certificate, add it to the system trust store
2. As a last resort (not recommended for production), disable SSL verification:
   ```bash
   export PYTHONHTTPSVERIFY=0
   ```

---

#### Symptom: Operations time out when cloning a large repository

**Cause**: The base repository is large and the clone operation exceeds the default timeout.

**Solution**: The agent uses shallow clones to minimise data transfer. If timeouts persist, check your network bandwidth and GitHub API rate limits:

```bash
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit
```

---

## 4. Unsupported resource types

#### Symptom: `Golden Module for 'elasticache' was not found in the inventory`

**Cause**: The requested resource type is not one of the 12 supported Golden Modules.

**Solution**: The agent will suggest the closest available alternative. The 12 supported types are:

| Resource type key        | Description                                      |
|--------------------------|--------------------------------------------------|
| `s3_bucket`              | Secure S3 bucket with encryption and versioning  |
| `ec2_instance`           | EC2 instance with security group and IAM role    |
| `rds_database`           | RDS database with encryption and backups         |
| `lambda_function`        | Lambda function with IAM role and logging        |
| `api_gateway`            | API Gateway with authentication and throttling   |
| `dynamodb_table`         | DynamoDB table with encryption and PITR          |
| `vpc`                    | VPC with public and private subnets              |
| `security_group`         | Security group with restrictive default rules    |
| `iam_role`               | IAM role with least-privilege policies           |
| `cloudwatch_log_group`   | CloudWatch log group with retention policies     |
| `sns_topic`              | SNS topic with encryption and access policies    |
| `sqs_queue`              | SQS queue with encryption and dead letter queue  |

List available types at any time:

```bash
bedrock-iac-agent list-resources
# or inside the session:
You> resources
```

---

#### Symptom: The agent misidentifies the resource type

**Cause**: The natural language request is ambiguous.

**Solution**: Be more explicit about the resource type:

```
# Ambiguous
You> I need a database

# Clear
You> I need a PostgreSQL RDS database called users-db in development
```

---

## 5. Tfvars generation errors

#### Symptom: `variables.tf not found` warning in logs

**Cause**: The agent cannot find the Golden Module directory locally. This is expected when running without a cloned base repository.

**Effect**: The agent falls back to built-in predefined schemas and continues normally. Generated tfvars are still valid.

**Solution**: This is not an error — no action required. If you want the agent to use the actual module schemas from your repository, clone the repository locally and set `modules_base_path` in your configuration.

---

#### Symptom: Generated tfvars file has unexpected parameter values

**Cause**: The agent applied naming conventions or default values that differ from your expectations.

**Solution**: Review the naming convention settings in `config.yaml`:

```yaml
naming:
  prefix: "mycompany"       # Prepended to all resource names
  environment_suffix: true  # Appends "-dev", "-prod", etc.
  separator: "-"
```

To disable the prefix, set it to an empty string:

```yaml
naming:
  prefix: ""
```

---

#### Symptom: `Parameter 'X' is required but was not provided`

**Cause**: The natural language request did not include a required parameter for the Golden Module.

**Solution**: The agent will ask for clarification. Provide the missing information:

```
You> Create a Lambda function in dev
Agent> What should the function be named, and which runtime should it use?

You> Call it image-resizer and use Python 3.11
Agent> ✅ Pull Request created: ...
```

---

#### Symptom: Security parameters appear in the tfvars with unexpected values

**Cause**: Security parameters are enforced by the Golden Module and cannot be overridden. The agent always sets them to their secure defaults.

**Effect**: This is by design. The following parameters are always set to their secure values regardless of what you request:

- `encryption_enabled = true` (S3)
- `versioning_enabled = true` (S3)
- `storage_encrypted = true` (RDS)
- `backup_retention_period = 7` (RDS)
- `enable_detailed_monitoring = true` (EC2)
- `enable_cloudwatch_logs = true` (Lambda)

If you need to change a security parameter, modify the Golden Module directly (outside the scope of this agent).

---

## 6. GitHub repository errors

#### Symptom: `Repository not found` or `404 Not Found`

**Cause**: The repository name or organisation is incorrect, or the token does not have access to the repository.

**Solution**:
1. Verify the organisation and repository name are correct (case-sensitive)
2. Confirm the token owner has at least `Read` access to the repository
3. Test access directly:
   ```bash
   curl -H "Authorization: token $GITHUB_TOKEN" \
     https://api.github.com/repos/$GITHUB_ORG/$GITHUB_REPO
   ```

---

#### Symptom: `Branch already exists`

**Cause**: A previous agent run created a branch with the same name that was not merged or deleted.

**Solution**: The agent generates unique branch names using timestamps (`iac-agent/{resource-type}/{environment}/{timestamp}`), so this should be rare. If it occurs:
1. Delete the old branch in GitHub
2. Re-run the request

---

#### Symptom: Pull Request is created but points to the wrong base branch

**Cause**: The target branch defaults to `main`. If your repository uses `master` or another default branch name, the PR target may be incorrect.

**Solution**: This is a known limitation. After the PR is created, update the base branch manually in the GitHub UI, or configure your repository to use `main` as the default branch.

---

#### Symptom: `Push rejected — protected branch`

**Cause**: The agent is trying to push directly to a protected branch (e.g., `main`).

**Solution**: This should not happen — the agent always creates a new feature branch. If you see this error, check that the branch naming pattern `iac-agent/*` is not accidentally covered by a branch protection rule.

---

## 7. CLI and startup issues

#### Symptom: `bedrock-iac-agent: command not found`

**Cause**: The package is not installed, or the virtual environment is not activated.

**Solution**:

```bash
# Activate the virtual environment
source venv/bin/activate

# Verify the package is installed
pip show bedrock-iac-agent

# Reinstall if needed
pip install -e .
```

---

#### Symptom: `ModuleNotFoundError: No module named 'bedrock_iac_agent'`

**Cause**: The package is not installed in the current Python environment.

**Solution**:

```bash
pip install -e .
# or with dev dependencies
pip install -e ".[dev]"
```

---

#### Symptom: Rich formatting is not displayed (no colours, no panels)

**Cause**: The `rich` library is not installed, or the terminal does not support ANSI colour codes.

**Solution**:

```bash
pip install rich
```

If the terminal does not support colours (e.g., a CI environment), the agent automatically falls back to plain text output.

---

#### Symptom: `KeyboardInterrupt` exits the session unexpectedly

**Cause**: Pressing `Ctrl-C` during input sends a `KeyboardInterrupt`.

**Solution**: This is expected behaviour — `Ctrl-C` exits the session cleanly. Use `Ctrl-D` (EOF) or type `exit` to exit without triggering an interrupt.

---

## 8. Bedrock model errors

#### Symptom: `ThrottlingException` from Bedrock

**Cause**: The Bedrock API rate limit has been reached.

**Solution**: The agent retries automatically with exponential backoff. If throttling persists:
1. Wait a few minutes before retrying
2. Switch to a different economic model:
   ```bash
   export BEDROCK_MODEL_ID="amazon.nova-micro-v1:0"
   ```
3. Request a quota increase in the AWS console under **Service Quotas → Amazon Bedrock**

---

#### Symptom: `ValidationException: The model is not supported in this region`

**Cause**: The selected Bedrock model is not available in the configured AWS region.

**Solution**: Check model availability by region in the [AWS Bedrock documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/models-regions.html) and switch to a supported region:

```bash
export AWS_DEFAULT_REGION="us-west-2"
```

Or update `config.yaml`:

```yaml
bedrock:
  region: "us-west-2"
```

---

#### Symptom: The agent asks for clarification on every request

**Cause**: The Bedrock model is returning low-confidence parses, possibly due to very short or ambiguous requests.

**Solution**: Provide more context in your requests:

```
# Too vague
You> I need a bucket

# Better
You> Create an S3 bucket called application-logs for the development environment
```

---

#### Symptom: The agent generates incorrect resource types

**Cause**: The natural language request uses terminology that maps to a different resource type.

**Solution**: Use the exact resource type names or common AWS service names:

| Instead of...          | Say...                                    |
|------------------------|-------------------------------------------|
| "object storage"       | "S3 bucket"                               |
| "serverless function"  | "Lambda function"                         |
| "NoSQL database"       | "DynamoDB table"                          |
| "relational database"  | "RDS database"                            |
| "message queue"        | "SQS queue"                               |
| "pub/sub topic"        | "SNS topic"                               |
| "REST API"             | "API Gateway"                             |
| "virtual network"      | "VPC"                                     |
| "firewall rules"       | "security group"                          |
| "log storage"          | "CloudWatch log group"                    |

---

## 9. Audit logging issues

#### Symptom: No log output is visible

**Cause**: The default log level may be set above the level of the messages you expect to see.

**Solution**: Increase the log level:

```bash
# Show INFO and above
export BEDROCK_IAC_LOG_LEVEL=INFO
bedrock-iac-agent chat

# Show DEBUG and above (very verbose)
export BEDROCK_IAC_LOG_LEVEL=DEBUG
bedrock-iac-agent chat
```

Or configure logging in Python:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

#### Symptom: Audit logs are not in JSON format

**Cause**: The Python logging configuration may have been overridden by another library.

**Solution**: The agent uses structured JSON logging by default. If you see plain text logs, check whether another library (e.g., `uvicorn`, `gunicorn`) is reconfiguring the root logger before the agent starts.

---

## 10. Installation and environment issues

#### Symptom: `pip install` fails with dependency conflicts

**Solution**: Use a fresh virtual environment:

```bash
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

---

#### Symptom: `python3 -m venv` fails on Ubuntu/Debian

**Cause**: The `python3-venv` package is not installed.

**Solution**:

```bash
sudo apt-get install python3-venv
python3 -m venv venv
```

---

#### Symptom: Tests fail with `ImportError`

**Cause**: The package is not installed in editable mode.

**Solution**:

```bash
pip install -e ".[dev]"
pytest
```

---

#### Symptom: `mypy` reports type errors after installation

**Cause**: Type stubs for optional dependencies may be missing.

**Solution**:

```bash
pip install types-PyYAML types-requests
mypy src/
```

---

## Getting further help

If your issue is not covered here:

1. Check the debug logs for more detail:
   ```bash
   export BEDROCK_IAC_LOG_LEVEL=DEBUG
   bedrock-iac-agent chat 2>&1 | tee debug.log
   ```

2. Review the audit log for structured error records (look for `"event_type": "error"` entries)

3. Run the test suite to verify your installation is healthy:
   ```bash
   pytest -m "not integration" -v
   ```

4. Open an issue in the repository with:
   - The exact error message
   - The relevant section of the debug log (with credentials redacted)
   - Your Python version (`python3 --version`)
   - Your operating system
