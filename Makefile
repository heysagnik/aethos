.PHONY: check lint types test migrations api-types frontend-check dev-backend dev-frontend

export DJANGO_SETTINGS_MODULE ?= aethos.settings.test
export MYPYPATH := backend:indexer
export PYTHONPATH := backend

check: lint types test migrations frontend-check

lint:
	uv run ruff check .
	uv run ruff format --check .

types:
	uv run mypy backend/core backend/apps indexer/aethos_indexer

test:
	uv run pytest

migrations:
	uv run python backend/manage.py makemigrations --check --dry-run

api-types:
	uv run python backend/manage.py export_openapi > frontend/openapi.json
	cd frontend && pnpm gen:api

frontend-check:
	cd frontend && pnpm typecheck && pnpm lint && pnpm test

dev-backend:
	DJANGO_SETTINGS_MODULE=aethos.settings.dev uv run python backend/manage.py runserver 8000

dev-frontend:
	cd frontend && pnpm dev
