.PHONY: help install dev lint format test test-unit test-integration up down migrate shell cli clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install -e .

dev: ## Install development dependencies
	pip install -e ".[dev]"

lint: ## Run linter (ruff)
	ruff check app/ tests/
	ruff format --check app/ tests/

format: ## Auto-format code
	ruff check --fix app/ tests/
	ruff format app/ tests/

test: ## Run all tests
	pytest tests/ -v --tb=short

test-unit: ## Run unit tests only
	pytest tests/unit/ -v --tb=short -m unit

test-integration: ## Run integration tests only
	pytest tests/integration/ -v --tb=short -m integration

test-cov: ## Run tests with coverage
	pytest tests/ -v --tb=short --cov=app --cov-report=term-missing --cov-report=html

up: ## Start services with docker-compose
	docker-compose up -d

down: ## Stop services
	docker-compose down

up-build: ## Rebuild and start services
	docker-compose up -d --build

migrate: ## Run database migrations
	alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create MSG="description")
	alembic revision --autogenerate -m "$(MSG)"

shell: ## Open a Python shell with app context
	python -c "import asyncio; asyncio.run(__import__('app.db.session', fromlist=['async_session']).async_session())"

logs: ## Tail docker-compose logs
	docker-compose logs -f

cli: ## Run the CLI tool (usage: make cli ARGS="health")
	python -m app.cli $(ARGS)

clean: ## Clean up caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf dist/ build/ *.egg-info/
