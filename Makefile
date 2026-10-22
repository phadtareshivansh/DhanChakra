# Dhan-Chakra — developer shortcuts. Run `make` or `make help`. 

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Docker Desktop on macOS keeps its CLI plugins here; a no-op elsewhere.
export PATH := /Applications/Docker.app/Contents/Resources/bin:$(PATH)

COMPOSE ?= $(shell command -v docker-compose >/dev/null 2>&1 && echo docker-compose || echo "docker compose")
API_SERVICE ?= api

.PHONY: help env up down restart logs ps bootstrap test test-all benchmark benchmark-amlsim benchmark-amlworld scale-test apply-schema smoke reset

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

benchmark: ## Run the model benchmark; refresh results.json, PR curve and the docs block
	$(COMPOSE) exec -T $(API_SERVICE) sh -c 'rm -rf /tmp/benchmark_out && python /benchmarks/run_benchmark.py --out-dir /tmp/benchmark_out --doc /docs/benchmarks.md --commit-hash "$(shell git describe --always --dirty)"'
	$(COMPOSE) cp $(API_SERVICE):/tmp/benchmark_out/results.json api/benchmarks/results.json
	$(COMPOSE) cp $(API_SERVICE):/tmp/benchmark_out/pr_curve.png api/benchmarks/pr_curve.png
	@echo "updated api/benchmarks/results.json, api/benchmarks/pr_curve.png and the generated block in docs/benchmarks.md"

benchmark-amlsim: ## Run the benchmark on our self-generated AMLSim-style dataset (A2)
	$(COMPOSE) exec -T $(API_SERVICE) sh -c 'rm -rf /tmp/benchmark_aml && python /benchmarks/run_benchmark.py --dataset amlsim --out-dir /tmp/benchmark_aml --doc "" --commit-hash "$(shell git describe --always --dirty)"'
	$(COMPOSE) exec -T $(API_SERVICE) sh -c 'python /benchmarks/run_ablation.py --dataset amlsim --out-dir /tmp/benchmark_aml'
	$(COMPOSE) exec -T $(API_SERVICE) sh -c 'python /benchmarks/run_fp_stress.py --dataset amlsim --out-dir /tmp/benchmark_aml'
	$(COMPOSE) cp $(API_SERVICE):/tmp/benchmark_aml/results_amlsim.json api/benchmarks/results_amlsim.json
	$(COMPOSE) cp $(API_SERVICE):/tmp/benchmark_aml/ablation_amlsim.json api/benchmarks/ablation_amlsim.json
	$(COMPOSE) cp $(API_SERVICE):/tmp/benchmark_aml/fp_stress_amlsim.json api/benchmarks/fp_stress_amlsim.json
	@echo "updated api/benchmarks/{results,ablation,fp_stress}_amlsim.json"

benchmark-amlworld: ## Run the benchmark on the real IBM AMLworld file (set AMLWORLD_PATH)
	@test -n "$(AMLWORLD_PATH)" || (echo "set AMLWORLD_PATH=/data/amlworld/<file>.csv (see docs/benchmarks.md)"; exit 1)
	$(COMPOSE) exec -T -e AMLWORLD_PATH="$(AMLWORLD_PATH)" $(API_SERVICE) sh -c 'rm -rf /tmp/benchmark_aw && python /benchmarks/run_benchmark.py --dataset amlworld --amlworld-path "$$AMLWORLD_PATH" --out-dir /tmp/benchmark_aw --doc "" --commit-hash "$(shell git describe --always --dirty)"'
	$(COMPOSE) exec -T -e AMLWORLD_PATH="$(AMLWORLD_PATH)" $(API_SERVICE) sh -c 'python /benchmarks/run_ablation.py --dataset amlworld --amlworld-path "$$AMLWORLD_PATH" --out-dir /tmp/benchmark_aw'
	$(COMPOSE) exec -T -e AMLWORLD_PATH="$(AMLWORLD_PATH)" $(API_SERVICE) sh -c 'python /benchmarks/run_fp_stress.py --dataset amlworld --amlworld-path "$$AMLWORLD_PATH" --out-dir /tmp/benchmark_aw'
	$(COMPOSE) cp $(API_SERVICE):/tmp/benchmark_aw/results_amlworld.json api/benchmarks/results_amlworld.json
	$(COMPOSE) cp $(API_SERVICE):/tmp/benchmark_aw/ablation_amlworld.json api/benchmarks/ablation_amlworld.json
	$(COMPOSE) cp $(API_SERVICE):/tmp/benchmark_aw/fp_stress_amlworld.json api/benchmarks/fp_stress_amlworld.json
	@echo "updated api/benchmarks/{results,ablation,fp_stress}_amlworld.json"

apply-schema: ## Apply Neo4j constraints/indexes (idempotent; needs a running stack)
	$(COMPOSE) exec -T $(API_SERVICE) python /benchmarks/apply_schema.py

migrate: ## Apply the Postgres schema migrations that have not been applied yet
	./scripts/apply_migrations.sh

scale-test: ## Run the A3 scale test (writes api/benchmarks/scale_results.json + docs/performance.md)
	$(COMPOSE) exec -T $(API_SERVICE) sh -c 'python /benchmarks/run_scale_test.py --sizes 10000 100000 500000 --endpoint-repeats 20 --stage-timeout 300 --profile --out /tmp/scale_results.json --doc /tmp/performance.md --commit-hash "$(shell git describe --always --dirty)"'
	$(COMPOSE) cp $(API_SERVICE):/tmp/scale_results.json api/benchmarks/scale_results.json
	$(COMPOSE) cp $(API_SERVICE):/tmp/performance.md docs/performance.md
	@echo "updated api/benchmarks/scale_results.json and docs/performance.md"

smoke: ## Health-check the API and the frontend	@curl -fsS http://localhost:8000/health; echo
	@curl -fsS -o /dev/null -w "frontend http %{http_code}\\n" http://localhost:5173

reset: ## Destructive: stop the stack and delete all data volumes
	$(COMPOSE) down -v
