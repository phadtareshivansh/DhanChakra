# Dhan-Chakra — developer shortcuts. Run `make` or `make help`. 

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Docker Desktop on macOS keeps its CLI plugins here; a no-op elsewhere.
export PATH := /Applications/Docker.app/Contents/Resources/bin:$(PATH)

COMPOSE ?= $(shell command -v docker-compose >/dev/null 2>&1 && echo docker-compose || echo "docker compose")
API_SERVICE ?= api

.PHONY: help env up down restart logs ps bootstrap test test-all smoke reset

help: ## Show this list of targets
	@grep -hE "^[a-z-]+:.*?## " $(MAKEFILE_LIST) | sort | awk -F":.*?## " "{printf \"  %-11s %s\\n\", \$$1, \$$2}"

env: ## Create .env from .env.example with freshly generated secrets
	@python3 scripts/init_env.py

up: ## Build (if needed) and start the whole stack in the background
	$(COMPOSE) up -d --build
	@echo "frontend http://localhost:5173  |  api http://localhost:8000/docs"

down: ## Stop the stack (data volumes are kept)
	$(COMPOSE) down

restart: ## Restart just the API (picks up python edits)
	$(COMPOSE) restart $(API_SERVICE)

ps: ## Show service status
	$(COMPOSE) ps

logs: ## Tail logs from all services
	$(COMPOSE) logs -f --tail 40

bootstrap: ## Load the sample dataset and run analytics (idempotent)
	@bash scripts/bootstrap_demo_data.sh

test: ## Run the API test suite
	$(COMPOSE) exec -T $(API_SERVICE) pytest tests -q

test-all: ## Seed the sample data, then run the full suite (no skips)
	@bash scripts/bootstrap_demo_data.sh
	$(COMPOSE) exec -T $(API_SERVICE) pytest tests -q

smoke: ## Health-check the API and the frontend
	@curl -fsS http://localhost:8000/health; echo
	@curl -fsS -o /dev/null -w "frontend http %{http_code}\\n" http://localhost:5173

reset: ## Destructive: stop the stack and delete all data volumes
	$(COMPOSE) down -v
