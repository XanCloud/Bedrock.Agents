# Example Requests for All 12 Golden Modules

This document provides natural language example requests for each of the 12 supported Golden Module resource types. Copy any of these into the interactive CLI session to get started.

Start the agent:

```bash
bedrock-iac-agent chat
```

---

## 1. S3 Bucket (`s3_bucket`)

**What it creates**: A secure S3 bucket with server-side encryption and versioning enabled by default.

**Key parameters**:
- `bucket_name` (required) — logical name for the bucket
- `environment` (required) — `dev`, `staging`, or `prod`
- `tags` (optional) — additional resource tags

**Example requests**:

```
Create an S3 bucket called data-lake for the development environment
```

```
I need a bucket to store application logs in production
```

```
Set up an S3 bucket named backups in staging with tags for the finance team
```

```
Create a bucket for storing ML training datasets in dev
```

```
I need an S3 bucket called static-assets for the production environment
```

**What the agent generates** (`environments/dev/s3_bucket.tfvars`):

```hcl
bucket_name = "data-lake-dev"   # Name of the S3 bucket
environment = "dev"             # Deployment environment
tags        = {}                # Additional tags for the bucket

# --- Security parameters (managed by Golden Module) ---
encryption_enabled = true       # Enable server-side encryption
versioning_enabled = true       # Enable versioning
```

---

## 2. EC2 Instance (`ec2_instance`)

**What it creates**: An EC2 instance with an attached security group, IAM role, and detailed CloudWatch monitoring.

**Key parameters**:
- `instance_name` (required) — logical name for the instance
- `instance_type` (required) — e.g., `t3.micro`, `t3.small`, `m5.large`
- `environment` (required)
- `ami_id` (optional) — defaults to latest Amazon Linux 2

**Example requests**:

```
I need a t3.micro EC2 instance called web-server for the dev environment
```

```
Provision an EC2 instance named batch-worker with instance type t3.small in production
```

```
Create a small EC2 instance for running background jobs in staging
```

```
Set up an EC2 instance called bastion-host using t3.nano in development
```

```
I need an m5.large EC2 instance named data-processor for the production environment
```

---

## 3. RDS Database (`rds_database`)

**What it creates**: An RDS database instance with storage encryption and automated backups (7-day retention by default).

**Key parameters**:
- `db_name` (required) — database identifier
- `engine` (required) — `postgres`, `mysql`, `mariadb`, etc.
- `environment` (required)
- `instance_class` (optional) — defaults to `db.t3.micro`

**Example requests**:

```
Create a PostgreSQL RDS database called users-db in development
```

```
I need a MySQL database for the production environment with a db.t3.small instance class
```

```
Set up an RDS database named analytics using PostgreSQL in staging
```

```
Create a MariaDB database called legacy-app in dev
```

```
I need a production PostgreSQL database called orders-db with a db.m5.large instance
```

---

## 4. Lambda Function (`lambda_function`)

**What it creates**: A Lambda function with an IAM execution role and CloudWatch log group. Logging is always enabled.

**Key parameters**:
- `function_name` (required) — function identifier
- `runtime` (required) — e.g., `python3.11`, `nodejs18.x`, `java17`
- `environment` (required)
- `memory_size` (optional) — MB, defaults to `128`
- `timeout` (optional) — seconds, defaults to `30`

**Example requests**:

```
Create a Lambda function called image-processor using Python 3.11 in dev
```

```
I need a Node.js Lambda function for the production environment with 512 MB memory
```

```
Set up a Lambda function named data-transformer with a 60-second timeout in staging
```

```
Create a Python 3.11 Lambda called email-sender with 256 MB memory in development
```

```
I need a Java 17 Lambda function called report-generator in production with a 5-minute timeout
```

---

## 5. API Gateway (`api_gateway`)

**What it creates**: An API Gateway REST API with authentication and request throttling configured.

**Key parameters**:
- `name` (required) — API name
- `environment` (required)

**Example requests**:

```
Create an API Gateway for the user-service in development
```

```
I need an API Gateway called payments-api in production
```

```
Set up an API Gateway for the notification service in staging
```

```
Create an API Gateway named mobile-backend in dev
```

```
I need a production API Gateway called partner-api for the integration service
```

---

## 6. DynamoDB Table (`dynamodb_table`)

**What it creates**: A DynamoDB table with encryption at rest and point-in-time recovery enabled.

**Key parameters**:
- `name` (required) — table name
- `environment` (required)

**Example requests**:

```
Create a DynamoDB table called sessions in development
```

```
I need a DynamoDB table for storing user preferences in production
```

```
Set up a DynamoDB table named events in staging
```

```
Create a DynamoDB table called feature-flags in dev
```

```
I need a production DynamoDB table called order-history for the e-commerce service
```

---

## 7. VPC (`vpc`)

**What it creates**: A VPC with public and private subnets across multiple availability zones.

**Key parameters**:
- `name` (required) — VPC name
- `environment` (required)

**Example requests**:

```
Create a VPC for the development environment
```

```
I need a VPC with public and private subnets in production
```

```
Set up a VPC called app-network in staging
```

```
Create a VPC named data-platform-vpc in dev
```

```
I need a production VPC called microservices-network for the platform team
```

---

## 8. Security Group (`security_group`)

**What it creates**: A security group with restrictive default rules (deny all inbound, allow all outbound).

**Key parameters**:
- `name` (required) — security group name
- `environment` (required)

**Example requests**:

```
Create a security group for the web tier in development
```

```
I need a security group called db-access in production
```

```
Set up a security group for the application servers in staging
```

```
Create a security group named lambda-egress in dev
```

```
I need a production security group called internal-api-sg for the backend services
```

---

## 9. IAM Role (`iam_role`)

**What it creates**: An IAM role with least-privilege policies attached.

**Key parameters**:
- `name` (required) — role name
- `environment` (required)

**Example requests**:

```
Create an IAM role for Lambda execution in development
```

```
I need an IAM role called ec2-s3-access in production
```

```
Set up an IAM role for the ECS task in staging
```

```
Create an IAM role named glue-job-role in dev
```

```
I need a production IAM role called cross-account-readonly for the audit team
```

---

## 10. CloudWatch Log Group (`cloudwatch_log_group`)

**What it creates**: A CloudWatch log group with a configurable retention policy.

**Key parameters**:
- `name` (required) — log group name (e.g., `/app/my-service`)
- `environment` (required)

**Example requests**:

```
Create a CloudWatch log group for the API service in development
```

```
I need a log group called /app/payments in production with 30-day retention
```

```
Set up a CloudWatch log group for Lambda logs in staging
```

```
Create a log group named /ecs/worker-service in dev
```

```
I need a production CloudWatch log group called /app/audit-trail for compliance logging
```

---

## 11. SNS Topic (`sns_topic`)

**What it creates**: An SNS topic with server-side encryption and access policies.

**Key parameters**:
- `name` (required) — topic name
- `environment` (required)

**Example requests**:

```
Create an SNS topic for order notifications in development
```

```
I need an SNS topic called alerts in production
```

```
Set up an SNS topic for deployment events in staging
```

```
Create an SNS topic named user-signup-events in dev
```

```
I need a production SNS topic called critical-alarms for the on-call team
```

---

## 12. SQS Queue (`sqs_queue`)

**What it creates**: An SQS queue with server-side encryption and a dead letter queue (DLQ) configured.

**Key parameters**:
- `name` (required) — queue name
- `environment` (required)

**Example requests**:

```
Create an SQS queue for processing image uploads in development
```

```
I need a queue called payment-events in production
```

```
Set up an SQS queue with a dead letter queue for the order service in staging
```

```
Create an SQS queue named email-delivery in dev
```

```
I need a production SQS queue called async-tasks for the background worker service
```

---

## Multi-turn conversation examples

The agent maintains context across turns in a session. You can refine requests iteratively:

```
You> I need an S3 bucket for storing logs
Agent> What environment should this be deployed to? (dev, staging, prod)

You> Development
Agent> What would you like to name the bucket?

You> application-logs
Agent> ✅ Pull Request created: https://github.com/my-org/my-infra-repo/pull/42
```

```
You> Create a Lambda function called data-processor in dev
Agent> ✅ Pull Request created: https://github.com/my-org/my-infra-repo/pull/43

You> Actually, make it 512 MB memory instead
Agent> ✅ Updated Pull Request created: https://github.com/my-org/my-infra-repo/pull/44
```

---

## Listing available resource types

Inside the CLI session, type `resources` or `list` to see all supported Golden Modules:

```
You> resources
```

Or from the command line:

```bash
bedrock-iac-agent list-resources
```
