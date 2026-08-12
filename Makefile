# HMSv2 dev commands
.PHONY: dev seed check reset test

dev: ## Migrate + seed (admin if missing) + start the full dev stack
	./scripts/run-dev.sh

seed: ## Idempotent seed: settings, system roles, admin, demo doctor
	cd backend && .venv/bin/alembic upgrade head && .venv/bin/python -m app.seed

check: ## Full pipeline: lint + tests + builds + live smoke
	./scripts/check.sh

reset: ## Wipe dev DBs and rebuild from migrations (loses dev data!)
	./scripts/reset-dev.sh

test-backend:
	cd backend && .venv/bin/pytest -q
