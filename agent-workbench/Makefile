.PHONY: test build-web lint lint-py lint-ts check e2e-offline up-athena-prod restart-billing-prod verify-athena-prod

COMPOSE_E2E = docker compose --env-file ../.env -f docker-compose.e2e.yml
COMPOSE_PROD = $(COMPOSE_E2E) -f docker-compose.athena-prod.yml

# ---------------------------------------------------------------------------
# 单元测试（不依赖 Postgres / MinIO / OpenSandbox）
# ---------------------------------------------------------------------------
test:
	python -m pytest tests/ -v

# ---------------------------------------------------------------------------
# 前端构建
# ---------------------------------------------------------------------------
build-web:
	cd web && npm run build

# ---------------------------------------------------------------------------
# Lint：Python 语法检查 + TypeScript 类型检查
# ---------------------------------------------------------------------------
lint: lint-py lint-ts

lint-py:
	python -c "from app.main import app; print('backend import OK')"
	python -m py_compile app/main.py
	python -m py_compile app/worker.py
	python -m py_compile app/scheduler.py
	python -m py_compile app/security.py
	@for f in app/routers/*.py app/services/*.py app/runner/*.py; do \
		python -m py_compile "$$f" || exit 1; \
	done
	@echo "all Python files compiled successfully"

lint-ts:
	cd web && npx tsc --noEmit

# ---------------------------------------------------------------------------
# 全量检查：lint + test + build
# ---------------------------------------------------------------------------
check: lint test build-web

# ---------------------------------------------------------------------------
# 离线 fake-agent 契约冒烟
# ---------------------------------------------------------------------------
e2e-offline:
	python e2e/run_e2e.py --offline-fake-agent-check

# ---------------------------------------------------------------------------
# 正式 Athena + AWS S3（读仓库根 .env，覆盖 e2e 的 MinIO/fixture）
# ---------------------------------------------------------------------------
up-athena-prod:
	$(COMPOSE_PROD) up -d workbench-api billing-worker workbench-scheduler workbench-web

restart-billing-prod:
	$(COMPOSE_PROD) up -d --force-recreate workbench-api billing-worker workbench-scheduler

verify-athena-prod:
	@echo "=== billing-worker (expect: no fixture, no minio endpoint) ==="
	@docker exec agent-workbench-billing-worker sh -c 'echo ATHENA_E2E_MODE=$$ATHENA_E2E_MODE; echo WORKBENCH_S3_ENDPOINT=$$WORKBENCH_S3_ENDPOINT; echo WORKBENCH_S3_BUCKET=$$WORKBENCH_S3_BUCKET; echo AWS_REGION=$$AWS_REGION'
