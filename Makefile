.PHONY: help dev dev-backend dev-frontend install test lint build docker-up docker-down seed clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Development ──

install: ## Install all dependencies
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

dev: ## Start both frontend and backend
	@echo "Starting DataFlow Platform..."
	$(MAKE) dev-backend & $(MAKE) dev-frontend &

dev-backend: ## Start FastAPI backend only
	cd backend && uvicorn main:app --reload --port 8000

dev-frontend: ## Start Next.js frontend only
	cd frontend && npm run dev

# ── Testing ──

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests
	cd backend && pytest -v --cov=app tests/

test-frontend: ## Run frontend tests
	cd frontend && npm test

# ── Linting ──

lint: lint-backend lint-frontend ## Lint all code

lint-backend: ## Lint Python code
	cd backend && ruff check app/ tests/

lint-frontend: ## Lint TypeScript code
	cd frontend && npm run lint

# ── Build ──

build: build-frontend ## Build for production

build-frontend: ## Build Next.js frontend
	cd frontend && npm run build

# ── Docker ──

docker-up: ## Start all services with Docker Compose
	docker-compose up --build -d

docker-down: ## Stop all Docker services
	docker-compose down

docker-logs: ## Tail Docker logs
	docker-compose logs -f

# ── Database ──

seed: ## Seed DuckDB with sample data
	cd scripts && python seed_db.py

migrate: ## Run PostgreSQL migrations
	cd backend && alembic upgrade head

# ── Cleanup ──

clean: ## Remove generated files
	rm -rf backend/__pycache__ frontend/.next frontend/node_modules
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
