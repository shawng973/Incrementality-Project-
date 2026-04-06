# Incremental Tool — backend convenience targets
#
# Usage:
#   make migrate           Apply all pending migrations to the database
#   make migrate-down      Roll back the most recent migration
#   make migrate-history   Show migration history
#   make migrate-new m="description"  Create a new auto-generated migration
#   make migrate-sql       Print the SQL for pending migrations without running them
#   make dev               Start the API server (local development)
#   make worker            Start the ARQ worker (local development)
#   make test              Run the full test suite
#   make lint              Run ruff linter

.PHONY: migrate migrate-down migrate-history migrate-new migrate-sql dev worker test lint

# ── Migrations ────────────────────────────────────────────────────────────────

migrate:
	alembic upgrade head

migrate-down:
	alembic downgrade -1

migrate-history:
	alembic history --verbose

# Usage: make migrate-new m="add foo to bar"
migrate-new:
	alembic revision --autogenerate -m "$(m)"

# Print SQL for all pending migrations without applying them
migrate-sql:
	alembic upgrade head --sql

# ── Development servers ───────────────────────────────────────────────────────

dev:
	uvicorn app.main:app --reload --port 8000

worker:
	python -m arq app.jobs.analysis_pipeline.WorkerSettings

# ── Testing & linting ─────────────────────────────────────────────────────────

test:
	pytest

lint:
	ruff check app tests
