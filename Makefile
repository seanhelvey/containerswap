# Shortcuts for the things that are genuinely multi-step. Everything else is run the
# normal way — `uv run pytest`, `uv run ruff check .`, `uv run fastapi dev` — so there
# is no second vocabulary to learn and nothing hidden behind a wrapper.
#
# Compose is given --env-file /dev/null because it reads .env for variable
# substitution by default, and .env holds the production connection string.

COMPOSE := docker compose --env-file /dev/null

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
	@uv run alembic upgrade head

down:  ## Stop Postgres, keeping data
	@$(COMPOSE) down

reset:  ## Throw the local database away and rebuild it
	@$(COMPOSE) down -v
	@$(MAKE) up

psql:  ## Open a shell on the local database
	@$(COMPOSE) exec db psql -U containerswap containerswap

logs:  ## Fetch recent production logs
	@uv run fastapi cloud logs --no-follow --tail 200 --since 1h
