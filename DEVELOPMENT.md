# Development Guide

## Project Structure

```
bedrock-iac-agent/
├── src/
│   └── bedrock_iac_agent/
│       ├── __init__.py          # Package initialization
│       ├── models.py            # Core data models
│       └── py.typed             # Type checking marker
├── tests/
│   ├── __init__.py
│   └── test_models.py           # Unit tests for data models
├── .gitignore                   # Git ignore patterns
├── pyproject.toml               # Project configuration and dependencies
├── README.md                    # Project documentation
├── DEVELOPMENT.md               # This file
└── LICENSE                      # MIT License
```

## Setup

### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
# Install package in editable mode with dev dependencies
pip install -e ".[dev]"
```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific test file
pytest tests/test_models.py

# Run with verbose output
pytest -v
```

### Code Quality

```bash
# Format code with black
black src/ tests/

# Lint with ruff
ruff check src/ tests/

# Fix linting issues automatically
ruff check --fix src/ tests/

# Type check with mypy
mypy src/
```

### Test Coverage

The project aims for >80% test coverage on core components. Current coverage:
- `models.py`: 100%

View detailed coverage report:
```bash
pytest --cov --cov-report=html
open htmlcov/index.html
```

## Core Data Models

All data models are defined in `src/bedrock_iac_agent/models.py`:

### Enums
- `ResourceType`: 12 AWS resource types supported by Golden Modules
- `Environment`: Deployment environments (dev, staging, prod)

### Request/Response Models
- `StructuredRequest`: Parsed user request
- `AgentResponse`: Response to user
- `ValidationResult`: Validation results

### Configuration Models
- `Parameter`: Golden Module parameter definition
- `ModuleSchema`: Golden Module schema
- `TfvarsContent`: Generated tfvars content
- `NamingConventions`: Naming rules

### GitHub Models
- `GitHubCredentials`: GitHub authentication
- `PullRequestDetails`: PR creation details
- `PullRequest`: Created PR information
- `FileChange`: File modification details

### Context Models
- `ConversationContext`: Multi-turn conversation state
- `ErrorResponse`: Structured error information
- `ModuleInfo`: Golden Module metadata

## Next Steps

After completing Task 1, the next tasks will implement:

1. **Task 2**: Golden Modules Inventory component
2. **Task 3**: Audit Logger component
3. **Task 5**: Natural Language Parser with Bedrock integration
4. **Task 6**: Configuration Generator
5. **Task 8**: GitHub Integration
6. **Task 11**: Bedrock IaC Agent orchestrator
7. **Task 12**: CLI Interface

## Dependencies

### Core Dependencies
- `boto3`: AWS SDK for Bedrock integration
- `PyGithub`: GitHub API client
- `click`: CLI framework
- `python-hcl2`: HCL parsing for Terraform

### Development Dependencies
- `pytest`: Testing framework
- `pytest-cov`: Coverage reporting
- `pytest-mock`: Mocking utilities
- `black`: Code formatter
- `ruff`: Fast Python linter
- `mypy`: Static type checker

## Contributing

1. Create a feature branch
2. Make changes
3. Run tests and ensure they pass
4. Run code quality checks
5. Submit a pull request

## Troubleshooting

### Virtual Environment Issues

If you encounter issues with the virtual environment:
```bash
# Remove existing venv
rm -rf venv

# Create fresh venv
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### Import Errors

If you get import errors, ensure the package is installed in editable mode:
```bash
pip install -e .
```

### Test Failures

If tests fail, check:
1. Virtual environment is activated
2. All dependencies are installed
3. Python version is 3.9 or higher
