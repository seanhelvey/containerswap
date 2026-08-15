# Shortcuts for the things that are genuinely multi-step. Everything else is run the
# normal way — `uv run pytest`, `uv run ruff check .`, `uv run fastapi dev` — so there
# is no second vocabulary to learn and nothing hidden behind a wrapper.
#
# Compose is given --env-file /dev/null because it reads .env for variable
# substitution by default, and .env holds the production connection string.
# The alembic call below overrides CS_DATABASE_URL / CS_MIGRATION_DATABASE_URL
# for the same reason, pointing both at the local container. migrations/env.py
# refuses to use CS_MIGRATION_DATABASE_URL without CS_CONFIRM_PROD_MIGRATION, so
# without this override `make up` would just fail rather than reach production —
# the override exists so routine local dev doesn't have to pass that flag.

COMPOSE := docker compose --env-file /dev/null
LOCAL_DB := postgresql+psycopg://containerswap:localdev@localhost:5433/containerswap

.DEFAULT_GOAL := help
.PHONY: help up down reset psql logs

help:  ## Show this help
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-8s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  Then run tests and the app the usual way:"
	@echo "    uv run pytest"
	@echo "    uv run fastapi dev"

up:  ## Start Postgres, wait for it, and apply migrations
	@$(COMPOSE) up -d
	@printf 'waiting for postgres'
	@until $(COMPOSE) exec -T db pg_isready -U containerswap >/dev/null 2>&1; do \
		printf '.'; sleep 1; \
	done
	@echo ' ready'
	@CS_DATABASE_URL=$(LOCAL_DB) CS_MIGRATION_DATABASE_URL= uv run alembic upgrade head

down:  ## Stop Postgres, keeping data
	@$(COMPOSE) down

reset:  ## Throw the local database away and rebuild it
	@$(COMPOSE) down -v
	@$(MAKE) up

psql:  ## Open a shell on the local database
	@$(COMPOSE) exec db psql -U containerswap containerswap

logs:  ## Fetch recent production logs
	@uv run fastapi cloud logs --no-follow --tail 200 --since 1h
