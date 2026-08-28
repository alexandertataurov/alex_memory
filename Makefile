PYTHON := .venv/bin/python
UV ?= .venv/bin/uv
LIMIT ?= 500

.PHONY: help setup hooks run daemon test test-fast coverage lint format format-check typecheck check lock-check deps audit verify health db-check db-backup repair-dry-run docs docs-check changes tasks review codex-hooks-check codex-check

help:
	@printf '%s\n' 'Alex Memory development commands:' \
	  '  make setup           Sync the locked development environment with uv.' \
	  '  make hooks           Install local pre-commit hooks and environments.' \
	  '  make run             Start the interactive terminal app.' \
	  '  make daemon          Start the local sync daemon.' \
	  '  make test            Run the test suite.' \
	  '  make lint            Run Ruff checks.' \
	  '  make format          Apply Ruff formatting.' \
	  '  make format-check    Check Ruff formatting.' \
	  '  make typecheck       Run mypy.' \
	  '  make check           Run the fast deterministic quality check.' \
	  '  make lock-check      Verify that uv.lock matches pyproject.toml.' \
	  '  make deps            Check declared Python dependencies with deptry.' \
	  '  make audit           Audit the synced environment for known vulnerabilities.' \
	  '  make verify          Run the complete local quality gate.' \
	  '  make health          Inspect local runtime prerequisites.' \
	  '  make db-check        Check SQLite integrity.' \
	  '  make db-backup       Create a SQLite API backup.' \
	  '  make repair-dry-run  Report an explicit bounded repair scope.' \
	  '  make docs            Regenerate derived documentation.' \
	  '  make docs-check      Verify generated documentation is current.' \
	  '  make changes         Report available change information.' \
	  '  make tasks           Show the current task queue.' \
	  '  make review          List code-size review signals.' \
	  '  make codex-hooks-check Validate the local Codex hook configuration.' \
	  '  make codex-check     Run the Codex workflow check.'

setup:
	$(UV) sync

hooks:
	$(PYTHON) -m pre_commit install --install-hooks

run:
	PYTHONPATH=src $(PYTHON) src/main.py

daemon:
	PYTHONPATH=src $(PYTHON) src/main.py --daemon

test:
	$(PYTHON) -m pytest

test-fast:
	$(PYTHON) -m pytest -q

coverage:
	$(PYTHON) -m pytest --cov=alex_memory --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check src tests scripts

format:
	$(PYTHON) -m ruff format src tests scripts

format-check:
	$(PYTHON) -m ruff format --check src tests scripts

typecheck:
	$(PYTHON) -m mypy src scripts

check:
	$(PYTHON) scripts/dev_tools.py check

lock-check:
	$(UV) lock --check

deps:
	$(UV) run --locked deptry .

audit:
	$(UV) run --locked pip-audit

verify:
	$(PYTHON) scripts/dev_tools.py verify

health:
	$(PYTHON) scripts/dev_tools.py health

db-check:
	$(PYTHON) scripts/dev_tools.py db-check

db-backup:
	$(PYTHON) scripts/dev_tools.py db-backup

repair-dry-run:
	@test -n "$(OPERATION)" || { echo "Set OPERATION to fts, task-project, segments, or context."; exit 2; }
	$(PYTHON) scripts/dev_tools.py repair-dry-run --operation "$(OPERATION)" --limit $(LIMIT)

docs:
	$(PYTHON) scripts/dev_tools.py docs

docs-check:
	$(PYTHON) scripts/dev_tools.py docs-check

changes:
	$(PYTHON) scripts/dev_tools.py changes

tasks:
	$(PYTHON) scripts/dev_tools.py tasks

review:
	$(PYTHON) scripts/dev_tools.py review

codex-hooks-check:
	$(PYTHON) .codex/hooks/check.py

codex-check:
	$(PYTHON) scripts/dev_tools.py codex-check
