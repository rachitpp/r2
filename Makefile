# POS Copilot — Phase 0
#
# Nothing in this file needs an API key. If a target asks for one, something
# has gone wrong (CLAUDE.md rule 1).

SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help up down db reset seed seed-generate verify-seed schema-doc \
        test lint fmt psql verify-corpus verify-parse db-roles \
        eval-sql eval-sql-stub eval-expectations seed-if-missing hooks \
        serve serve-live web web-check corpus corpus-verify ingest ingest-verify \
        extract extract-stub corpus-checksums eval-extraction injection-demo \
        embed test-slow demo-beat-2 smoke

-include .env

POSTGRES_USER ?= postgres
POSTGRES_DB   ?= pos
POSTGRES_PORT ?= 5432
SEED_SIZE     ?= small
API_PORT ?= 8000
TEMPLATE_DB   := $(POSTGRES_DB)_template
POS_APP_PASSWORD      ?= pos_app_dev
POS_READONLY_PASSWORD ?= pos_readonly_dev

# What the serving layer reads from its environment.
#
# `-include .env` makes these *make* variables, not environment ones, so a
# recipe that does not pass them on gets none of them: `make serve` in a shell
# that has never sourced .env was answering every query with
# "READONLY_DATABASE_URL is not set" while still reporting healthy. Exporting
# them is what makes the target able to do the thing it is named for.
READONLY_DATABASE_URL ?= postgresql://pos_readonly:$(POS_READONLY_PASSWORD)@localhost:$(POSTGRES_PORT)/$(POSTGRES_DB)
AS_OF_DATE   ?= 2026-06-30
SQL_MAX_ROWS ?= 100
DEMO_MODE    ?= true
export READONLY_DATABASE_URL AS_OF_DATE SQL_MAX_ROWS DEMO_MODE

# Model config, for the local targets that spend quota. Never reaches CI: CI
# runs with no key, and every target that needs one is here (rule 1).
export MODEL_PLAN MODEL_CLASSIFY MODEL_EXTRACT GEMINI_API_KEY
export GOOGLE_APPLICATION_CREDENTIALS
export VERTEX_LOCATION VERTEX_RPM GEMINI_RPM LIVE_MAX_CALLS LIVE_MAX_SPEND_USD

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

up: ## Start the database (skipped when EXTERNAL_DB is set)
	@# `up` starts the local compose service. When the database lives somewhere
	@# this Makefile does not own — a hosted instance, or a CI service container —
	@# there is nothing to start, and running `docker compose up` would either
	@# fail for want of Docker or bind a second Postgres onto the same port.
	@#
	@# The readiness wait still runs in both cases. That is the part worth
	@# keeping: it proves the database this build is about to write to is
	@# actually reachable, which is a different claim from "a container started".
	@if [ -n "$(EXTERNAL_DB)" ]; then \
	  echo "==> EXTERNAL_DB set; not starting compose"; \
	else \
	  docker compose up -d db; \
	fi
	@until $(PSQL) -d postgres -q -c 'SELECT 1' >/dev/null 2>&1; do sleep 0.3; done
	@echo "db ready"

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

eval-sql: ## Run the SQL eval set (COSTS QUOTA — never in CI, ADR-0005)
	@cd api && $(UV) run python scripts/eval_sql.py $(EVAL_ARGS)

eval-sql-stub: ## Same runner against a stub — no key, no quota, no network
	@cd api && $(UV) run python scripts/eval_sql.py --provider stub $(EVAL_ARGS)

eval-expectations: ## Recompute expected result sets in evals/sql/questions.jsonl
	@cd api && $(UV) run python scripts/eval_expectations.py \
	  --database-url "$${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/$(POSTGRES_DB)}"

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

hooks: ## Enable the repo's git hooks (credential scan on commit)
	@git config core.hooksPath .githooks
	@echo "==> core.hooksPath = .githooks; pre-commit credential scan active"

psql: ## Interactive psql against the working database
	@docker compose exec db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

web: ## Run the web app (needs `make serve` in another shell)
	cd web && npm run dev

web-check: ## Typecheck and build the web app
	cd web && npx tsc --noEmit && npm run build

serve: ## Run the query API (demo mode by default — no key, no quota)
	@# PYTHONPATH rather than a build backend: pyproject.toml declares none on
	@# purpose, and pytest reaches src/ the same way.
	cd api && PYTHONPATH=src $(UV) run uvicorn pos_copilot.app:app --reload --port $(API_PORT)

serve-live: ## Run the query API on the LIVE model path (SPENDS YOUR OWN QUOTA)
	@# A separate target, not a flag on `serve`, because the spend should be
	@# something you typed. The ceiling is in api/src/pos_copilot/live.py and
	@# defaults to 50 calls / $1.00 — raise LIVE_MAX_CALLS deliberately.
	@if [ -z "$$MODEL_PLAN" ]; then \
	  echo "MODEL_PLAN is not set. Pin an exact model string in .env — a"; \
	  echo "floating alias makes a result file describe nothing."; exit 1; \
	fi
	@echo "==> live: $$MODEL_PLAN, ceiling $${LIVE_MAX_CALLS:-50} calls / \$$$${LIVE_MAX_SPEND_USD:-1.00}"
	cd api && PYTHONPATH=src DEMO_MODE=false $(UV) run uvicorn pos_copilot.app:app --reload --port $(API_PORT)

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

# The documents verify-parse re-parses. See the target for why these.
#
# invoice-sup-12-5436 is the load-bearing one and was added 2026-08-11 after the
# original three turned out to share a property that made the check useless: all
# three parse identically on every platform tried, so verify-parse passed on a
# machine that reproduced only 34 of 38 documents. This one does NOT — it parses
# to a markdown table on the reference Linux environment and to the bare word
# "Supplier" on Windows. A sample that cannot fail is not a sample.
VERIFY_PARSE_DOCS ?= contract-sup-01-20241130,catalog-sup-01-20251103,contract-sup-01-20250629,invoice-sup-12-5436

corpus: ## Generate the synthetic corpus from the seeded database
	@# Needs the `corpus` dependency group (reportlab, pymupdf, pillow). They are
	@# generation-only and are NOT runtime dependencies of api/.
	cd api && $(UV) run --group corpus python scripts/corpus_generate.py \
	  --database-url "$${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/$(POSTGRES_DB)}"

corpus-verify: ## Regenerate into a temp dir and assert byte-identity
	@# The claim is that the corpus is reproducible, so it gets asserted rather
	@# than stated. PDF writers stamp timestamps and random /ID values by
	@# default; both are pinned, and this is what catches it if that regresses.
	@tmp=$$(mktemp -d); \
	  mkdir -p $$tmp/sources; \
	  (cd api && $(UV) run --group corpus python scripts/corpus_generate.py \
	     --database-url "$${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/$(POSTGRES_DB)}" \
	     --out $$tmp >/dev/null) && \
	  if diff -r -q corpus/sources $$tmp/sources && \
	     diff -q corpus/MANIFEST.csv $$tmp/MANIFEST.csv; then \
	    echo "corpus is byte-identical on regeneration"; rm -rf $$tmp; \
	  else \
	    echo "CORPUS IS NOT REPRODUCIBLE — see $$tmp"; exit 1; \
	  fi

ingest: ## Parse every corpus document with Docling into corpus/parsed/
	@# No model calls and no key: parsing is local. The extraction step that
	@# follows is the one that spends quota.
	cd api && $(UV) run --group corpus python scripts/corpus_ingest.py

ingest-verify: ## Re-parse into a temp dir and assert byte-identity
	@tmp=$$(mktemp -d); \
	  (cd api && $(UV) run --group corpus python scripts/corpus_ingest.py \
	     --out $$tmp >/dev/null) && \
	  if diff -r -q corpus/parsed $$tmp; then \
	    echo "parsed output is byte-identical on re-parse"; rm -rf $$tmp; \
	  else \
	    echo "PARSE IS NOT REPRODUCIBLE — see $$tmp"; exit 1; \
	  fi

extract: ## Extract structured data from the parsed corpus (SPENDS QUOTA)
	@# A separate target from extract-stub, not a flag, because the spend should
	@# be something you typed. 40 documents is 40 calls, ~$$0.80; the ceiling is
	@# 60 calls / $$2.00 and lives in the runner. Responses cache permanently, so
	@# re-running after a validator change costs nothing.
	@if [ -z "$$MODEL_EXTRACT" ]; then \
	  echo "MODEL_EXTRACT is not set. Pin an exact model string in .env — a"; \
	  echo "floating alias makes an extraction result describe nothing."; exit 1; \
	fi
	cd api && $(UV) run python scripts/corpus_extract.py $(EXTRACT_ARGS)

extract-stub: ## Same runner against a stub — no key, no quota, no network
	@# Writes to a temp directory. The runner also refuses a stub run aimed at
	@# corpus/extracted/, because invented values sitting in a committed
	@# directory are indistinguishable from extracted ones.
	@tmp=$$(mktemp -d); \
	  (cd api && $(UV) run python scripts/corpus_extract.py \
	     --provider stub --out "$$tmp" $(EXTRACT_ARGS)); \
	  status=$$?; rm -rf $$tmp; exit $$status

eval-extraction: ## Score corpus/extracted/ against the rows it came from
	@# No model calls — reads committed JSON and queries Postgres, so it is free
	@# to re-run. It needs a database and therefore never runs in CI (ADR-0005).
	@#
	@# The gold set is DERIVED, not hand-labelled: this corpus was generated from
	@# the database, so MANIFEST.csv's source_table + source_key name the row
	@# behind every document. That is exact and covers all 40 with no
	@# hand-labelling error. What it cannot do is tell a model failure from a
	@# DOCUMENT failure — see corpus/corrections/, where two of the four notes
	@# say the pipeline was right and the corpus was wrong.
	@if [ -z "$$DATABASE_URL" ]; then \
	  echo "DATABASE_URL is not set. The gold set is read from the rows the"; \
	  echo "documents were generated from; there is nothing to score without it."; \
	  exit 1; \
	fi
	cd api && $(UV) run python scripts/eval_extraction.py \
	  --gold-out ../corpus/gold/gold.json --json-out ../corpus/gold/score.json

smoke: ## Drive both demo beats through the web app's own request path
	@# Hits port 3000, NOT 8000, on purpose. pytest exercises FastAPI directly and
	@# tsc/next build check the web app compiles; neither touches the Next rewrite
	@# between them, so a typo there breaks every browser request while both suites
	@# stay green. This is the only check that would notice.
	@#
	@# Needs `make serve` and `make web` running. No key, no quota.
	@#
	@# It does NOT cover React event wiring — a button whose onClick was never
	@# attached passes this and passes CI. That needs a browser.
	cd api && $(UV) run python scripts/smoke_demo.py $(SMOKE_ARGS)

demo-beat-2: ## Produce the Phase 3 artifact — temporal + injection (SPENDS QUOTA)
	@# PLAN.md's Phase 3 done-condition, both halves, end to end against the real
	@# database and the real model. 3 calls, ~$$0.01, ceiling 8 calls / $$0.30.
	@#
	@# The injection half PLANTS a poisoned document in doc_chunks, embeds it with
	@# no special casing, and lets the retriever surface it on its own merits —
	@# the whole path a real attack takes, rather than handing a specimen to a
	@# prompt. The poison is removed again unless --keep-poison is passed.
	@if [ -z "$$DATABASE_URL" ] || [ -z "$$MODEL_PLAN" ]; then \
	  echo "DATABASE_URL and MODEL_PLAN must both be set."; exit 1; \
	fi
	cd api && $(UV) run --group retrieval python scripts/demo_beat2.py $(DEMO_ARGS)

embed: ## Load corpus/ into supplier_term_clauses and doc_chunks (no model calls)
	@# Embeddings are LOCAL — bge-small-en-v1.5 on CPU, no key and no quota
	@# (CLAUDE.md rule 2). The first run downloads ~130MB of weights from
	@# HuggingFace; that is a model download, not a model call.
	@#
	@# Idempotent by content hash: a chunk whose text has not changed keeps its
	@# vector, so a re-run after a parse change re-embeds only what moved.
	@if [ -z "$$DATABASE_URL" ]; then \
	  echo "DATABASE_URL is not set."; exit 1; \
	fi
	cd api && $(UV) run --group retrieval python scripts/embed_corpus.py $(EMBED_ARGS)

test-slow: ## Run the tests that load the embedding model (deselected by default)
	@# These are the assertions that catch a pooling or prefix change, which is
	@# invisible otherwise — the vectors keep their shape and retrieval quietly
	@# degrades. Run them at phase boundaries, not just on every commit.
	cd api && $(UV) run --group retrieval pytest -m slow

injection-demo: ## Run the injection specimens through both prompts (SPENDS QUOTA)
	@# Done-condition 5 wants a trace of the NAIVE path following an injection,
	@# so this deliberately runs api/prompts/retrieval_answer_unsafe.md — rule 6's
	@# one sanctioned violation, labelled at the top of that file.
	@#
	@# --runs 3 rather than 1 because two single runs of this disagreed with each
	@# other. 24 calls, ~$$0.09, ceiling 30 calls / $$0.30. The raw answers land in
	@# corpus/injection/traces/SUMMARY.json, so `--rescore` recomputes verdicts
	@# for nothing when the detector changes — and it changed four times.
	@if [ -z "$$MODEL_PLAN" ]; then \
	  echo "MODEL_PLAN is not set. Pin an exact model string in .env."; exit 1; \
	fi
	cd api && $(UV) run python scripts/injection_demo.py \
	  --runs 3 --max-calls 30 --max-spend 0.30 $(INJECTION_ARGS)

corpus-checksums: ## Regenerate corpus/CHECKSUMS.txt from what is on disk
	@# A deliberate act, like seed-generate. `make ingest` does it automatically
	@# because it is the last stage that writes artifacts; this is for the cases
	@# where it did not, and for adding a new artifact tree.
	cd api && $(UV) run python scripts/corpus_checksums.py

verify-corpus: ## SHA-256 every corpus artifact against corpus/CHECKSUMS.txt
	@# Now covers parsed/ and extracted/ as CONVENTIONS.md and ADR-0006 always
	@# said it did. It never did: it listed the source PDFs plus MANIFEST.csv and
	@# checked completeness by counting PDFs, so it passed 41/41 while checking
	@# none of the parse output.
	@#
	@# The completeness half is the part that matters and the part `sha256sum -c`
	@# cannot do — that verifies what the file mentions and is blind to what it
	@# omits, which is exactly how the gap survived. Python, not shell, because
	@# comparing two sets and saying which side each difference is on is what
	@# went wrong when it was counted instead.
	cd api && $(UV) run python scripts/corpus_checksums.py --check

verify-parse: ## Re-run Docling on the committed sample and assert byte-identity
	@# The sample spans the pipeline's failure modes rather than being the three
	@# fastest documents: a scanned page with no text layer at all (OCR is where
	@# parse accuracy is actually decided), a line-item table that continues
	@# across a page break, and a plain text-layer contract as the control. A
	@# sample that skipped OCR would assert the half that was never in doubt.
	@#
	@# No key and no quota — docling runs locally (ADR-0006). It does fetch its
	@# layout weights from HuggingFace on a cold cache, so the first CI run is
	@# slow; that is a model download, not a model call.
	@if [ ! -d corpus/parsed ]; then \
	  echo "skip: corpus/parsed/ does not exist yet (Phase 2)"; \
	else \
	  tmp=$$(mktemp -d); \
	  (cd api && $(UV) run --group corpus python scripts/corpus_ingest.py \
	     --only "$(VERIFY_PARSE_DOCS)" --out "$$tmp" >/dev/null) \
	     || { echo "verify-parse: the parse itself failed"; rm -rf $$tmp; exit 1; }; \
	  checked=0; fail=0; \
	  for id in $$(echo "$(VERIFY_PARSE_DOCS)" | tr ',' ' '); do \
	    if [ ! -s "$$tmp/$$id.md" ]; then \
	      echo "verify-parse: $$id produced no output"; fail=1; continue; \
	    fi; \
	    if diff -q "corpus/parsed/$$id.md" "$$tmp/$$id.md" >/dev/null 2>&1; then \
	      checked=$$(( checked + 1 )); \
	    else \
	      echo "PARSE IS NOT REPRODUCIBLE: $$id differs from the committed copy"; \
	      fail=1; \
	    fi; \
	  done; \
	  want=$$(echo "$(VERIFY_PARSE_DOCS)" | tr ',' ' ' | wc -w); \
	  if [ "$$checked" != "$$want" ] || [ "$$fail" != "0" ]; then \
	    echo "verify-parse FAILED ($$checked/$$want matched) — see $$tmp"; exit 1; \
	  fi; \
	  rm -rf $$tmp; \
	  echo "verify-parse: $$checked/$$want byte-identical to the committed parse"; \
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
