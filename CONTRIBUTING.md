# Contributing to AgentMemoryDB

Thank you for your interest in contributing to AgentMemoryDB! This document provides guidelines and information for contributors.

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally
3. **Set up** the development environment
4. **Create a branch** for your changes
5. **Make your changes** and add tests
6. **Submit a pull request**

## Development Setup

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 15+ with pgvector (or use docker-compose)

### Quick Setup

```bash
# Clone and enter the project
git clone https://github.com/YOUR_USERNAME/agentmemorydb.git
cd agentmemorydb

# Start Postgres with pgvector
docker-compose up -d db

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate  # Windows

# Install development dependencies
pip install -e ".[dev]"

# Set up pre-commit hooks
pre-commit install

# Copy and adjust env
cp .env.example .env

# Run migrations
alembic upgrade head

# Run tests
pytest tests/ -v
```

## Code Style

- We use **ruff** for linting and **black** for formatting
- Run `make lint` to check and `make format` to auto-fix
- Use type hints everywhere
- Add docstrings to public functions and classes
- Keep modules focused and small

## Testing

- Write tests for all new functionality
- Use `pytest` with async support
- Place unit tests in `tests/unit/` and integration tests in `tests/integration/`
- Mark tests appropriately: `@pytest.mark.unit` or `@pytest.mark.integration`
- Aim for meaningful tests, not just coverage numbers

```bash
# Run all tests
make test

# Run only unit tests
make test-unit

# Run only integration tests
make test-integration

# Run with coverage
make test-cov
```

## Pull Request Process

1. Update documentation if you change public APIs
2. Add tests for new functionality
3. Ensure all tests pass
4. Update the CHANGELOG if applicable
5. Use descriptive commit messages following [Conventional Commits](https://www.conventionalcommits.org/)

### Commit Message Format

```
type(scope): description

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## Reporting Issues

- Use GitHub Issues
- Include steps to reproduce
- Include relevant logs and error messages
- Specify your environment (OS, Python version, PostgreSQL version)

## Architecture Guidelines

- **Repository pattern** for database access
- **Service layer** for business logic
- **Pydantic schemas** for validation and serialization
- **FastAPI routes** should be thin — delegate to services
- Memory pipeline: Event → Observation → Memory (never skip steps)
- All retrieval should be logged for auditability

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
