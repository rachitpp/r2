# POS Copilot — Phase 0
#
# Nothing in this file needs an API key. If a target asks for one, something
# has gone wrong (CLAUDE.md rule 1).

SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help up down db reset seed seed-generate verify-seed schema-doc \
        test lint fmt psql verify-corpus verify-parse db-roles

-include .env

POSTGRES_USER ?= postgres
POSTGRES_DB   ?= pos
SEED_SIZE     ?= small
TEMPLATE_DB   := $(POSTGRES_DB)_template
POS_APP_PASSWORD      ?= pos_app_dev
POS_READONLY_PASSWORD ?= pos_readonly_dev

# Every psql invocation goes through this. It defaults to running inside the
# db container so no local psql client is needed; CI overrides it with a bare
# client:  make db PSQL="psql -v ON_ERROR_STOP=1 -h localhost -U postgres"
PSQL ?= docker compose exec -T db psql -v ON_ERROR_STOP=1 -U $(POSTGRES_USER)

# Seed generation runs inside a digest-pinned image. Byte-identical output is a
# definition-of-done item, and bare Python does not deliver it across machines:
# libm differences can flip a Poisson draw and the tzdata version moves
# timestamps. Pinning the image pins both. CI runs the identical command.
PY_IMAGE := python:3.12-slim@sha256:646fb0bca3dd3ea1bcc6feb72c17ed16eed6e10cffc732fcc1478bd3e7f02d7b
PY_RUN   := docker run --rm -u $(shell id -u):$(shell id -g) \
              -v $(CURDIR):/w -w /w \
              -e PYTHONHASHSEED=0 -e PYTHONDONTWRITEBYTECODE=1 \
              $(PY_IMAGE)

UV ?= uv

help: ## Show this help
	@echo "POS Copilot — Phase 0 targets"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-16s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  SEED_SIZE=$(SEED_SIZE)  (small = dev loop, full = demo build)"
	@echo "  Evals always run against full. See docs/PROGRESS.md."

up: ## Start the database
	docker compose up -d db
	@until $(PSQL) -d postgres -q -c 'SELECT 1' >/dev/null 2>&1; do sleep 0.3; done
	@echo "db ready on port $${POSTGRES_PORT:-5432}"

down: ## Stop the database (keeps the volume)
	docker compose down

db: up seed-if-missing ## Full rebuild: migrations + seed into a template, then clone it
	@echo "==> dropping databases"
	-@$(PSQL) -d postgres -q -c "ALTER DATABASE $(TEMPLATE_DB) IS_TEMPLATE false" 2>/dev/null
	@$(PSQL) -d postgres -q -c "DROP DATABASE IF EXISTS $(POSTGRES_DB) WITH (FORCE)"
	@$(PSQL) -d postgres -q -c "DROP DATABASE IF EXISTS $(TEMPLATE_DB) WITH (FORCE)"
	@$(PSQL) -d postgres -q -c "CREATE DATABASE $(TEMPLATE_DB)"
	@echo "==> applying migrations"
	@for f in migrations/*.sql; do \
	  echo "    $$f"; \
	  $(PSQL) -d $(TEMPLATE_DB) -q -f - < $$f || exit 1; \
	done
	@$(MAKE) --no-print-directory db-roles
	@$(MAKE) --no-print-directory seed
	@echo "==> marking $(TEMPLATE_DB) as a template"
	@$(PSQL) -d postgres -q -c "ALTER DATABASE $(TEMPLATE_DB) IS_TEMPLATE true"
	@$(MAKE) --no-print-directory reset

db-roles: ## Set role passwords from .env (roles themselves are made by 001)
	@$(PSQL) -d postgres -q \
	  -c "ALTER ROLE pos_app PASSWORD '$(POS_APP_PASSWORD)'" \
	  -c "ALTER ROLE pos_readonly PASSWORD '$(POS_READONLY_PASSWORD)'"

reset: ## Recreate the working database from the template (fast — a file copy)
	@$(PSQL) -d postgres -q -c "DROP DATABASE IF EXISTS $(POSTGRES_DB) WITH (FORCE)"
	@$(PSQL) -d postgres -q -c "CREATE DATABASE $(POSTGRES_DB) TEMPLATE $(TEMPLATE_DB)"
	@echo "==> $(POSTGRES_DB) ready (from $(TEMPLATE_DB))"

seed: ## COPY the seed CSVs into the template, then refresh derived objects
	@echo "==> loading seed/$(SEED_SIZE)"
	@for f in seed/$(SEED_SIZE)/*.csv; do \
	  t=$$(basename $$f .csv | sed 's/^[0-9]*_//'); \
	  printf '    %-24s' $$t; \
	  $(PSQL) -d $(TEMPLATE_DB) -q \
	    -c "\copy $$t FROM STDIN WITH (FORMAT csv, HEADER true)" < $$f || exit 1; \
	  echo ok; \
	done
	@echo "==> resetting identity sequences past the seeded ids"
	@$(PSQL) -d $(TEMPLATE_DB) -q -c "$$SETVAL_SQL"
	@echo "==> refreshing daily_product_sales"
	@$(PSQL) -d $(TEMPLATE_DB) -q -c "REFRESH MATERIALIZED VIEW daily_product_sales"
	@$(PSQL) -d $(TEMPLATE_DB) -q -c "ANALYZE"

seed-if-missing:
	@test -f seed/$(SEED_SIZE)/001_stores.csv || { \
	  echo "==> seed/$(SEED_SIZE) is absent; regenerating and verifying"; \
	  $(PY_RUN) python api/scripts/seed.py --size $(SEED_SIZE) --verify; \
	}

# --verify, not a plain regenerate. seed/full/ is gitignored, so this fires on
# every fresh clone; a plain regenerate would rewrite seed/CHECKSUMS.txt with
# whatever the local machine produced, which is exactly the silent drift the
# checksums exist to catch. Updating them is only ever a deliberate act
# (seed-generate).
seed-generate: ## Regenerate the seed CSVs for SEED_SIZE and update CHECKSUMS.txt
	@echo "==> generating seed/$(SEED_SIZE) in $(PY_IMAGE)"
	@$(PY_RUN) python api/scripts/seed.py --size $(SEED_SIZE)

verify-seed: ## Regenerate into a temp dir and assert it matches seed/CHECKSUMS.txt
	@$(PY_RUN) python api/scripts/seed.py --size $(SEED_SIZE) \
	  --out /tmp/verify-$(SEED_SIZE) --verify

schema-doc: ## Regenerate api/prompts/context/schema.md from the database COMMENTs
	@mkdir -p api/prompts/context
	@{ \
	  echo "<!-- Generated by \`make schema-doc\` from the COMMENTs in"; \
	  echo "     migrations/001_core_schema.sql. Do not hand-edit: edit the"; \
	  echo "     COMMENT ON statements in the migration and regenerate, so the"; \
	  echo "     documentation the model reads cannot drift from the schema."; \
	  echo "     business_context.md, next door, IS hand-written. -->"; \
	  echo; \
	  echo "# Schema"; \
	  echo; \
	  echo "Tables first, then materialized views, then views."; \
	  echo; \
	  $(PSQL) -d $(POSTGRES_DB) -X -q -t -A -F '' -f - < api/scripts/schema_doc.sql; \
	} > api/prompts/context/schema.md
	@echo "==> wrote api/prompts/context/schema.md"

psql: ## Interactive psql against the working database
	@docker compose exec db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

test: ## Run pytest
	cd api && $(UV) run pytest

lint: ## ruff check + format check
	cd api && $(UV) run ruff check . && $(UV) run ruff format --check .

fmt: ## ruff format
	cd api && $(UV) run ruff format . && $(UV) run ruff check --fix .

# ─── Phase 2 targets ─────────────────────────────────────────────────────────
# These exist now so CI's shape never changes when the corpus lands. They skip
# cleanly while corpus/CHECKSUMS.txt is absent and fail loudly once it is not —
# a permanently-passing no-op would be worse than having no check at all.

verify-corpus: ## SHA-256 every corpus artifact against corpus/CHECKSUMS.txt
	@if [ ! -f corpus/CHECKSUMS.txt ]; then \
	  echo "skip: corpus/CHECKSUMS.txt does not exist yet (Phase 2)"; \
	else \
	  sha256sum -c corpus/CHECKSUMS.txt; \
	fi

verify-parse: ## Re-run Docling on the committed sample and assert byte-identity
	@if [ ! -d corpus/parsed ]; then \
	  echo "skip: corpus/parsed/ does not exist yet (Phase 2)"; \
	else \
	  echo "ERROR: corpus/parsed/ exists but verify-parse is not implemented."; \
	  exit 1; \
	fi

define SETVAL_SQL_BODY
DO $$$$
DECLARE r record; m bigint;
BEGIN
  FOR r IN
    SELECT c.table_name, c.column_name,
           pg_get_serial_sequence(quote_ident(c.table_name), c.column_name) AS seq
    FROM information_schema.columns c
    WHERE c.table_schema = 'public' AND c.is_identity = 'YES'
    ORDER BY c.table_name, c.column_name
  LOOP
    IF r.seq IS NULL THEN CONTINUE; END IF;
    EXECUTE format('SELECT coalesce(max(%I), 0) FROM %I', r.column_name, r.table_name)
      INTO m;
    PERFORM setval(r.seq, GREATEST(m, 1), m > 0);
  END LOOP;
END
$$$$;
endef
export SETVAL_SQL := $(SETVAL_SQL_BODY)
