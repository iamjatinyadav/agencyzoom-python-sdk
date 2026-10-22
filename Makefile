# Every target uses uv (https://docs.astral.sh/uv/). `make help` lists them.
PYTHONS ?= 3.8 3.9 3.10 3.11 3.12 3.13 3.14

.PHONY: help install generate lint format typecheck test test-all check build clean

help:  ## Show available targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install:  ## Create .venv with all dev dependencies
	uv sync

generate:  ## Regenerate models (from the spec) and the sync client (from _async/)
	uv run python scripts/generate_models.py
	uv run python scripts/unasync.py

lint:  ## Lint and check formatting
	uv run ruff check src tests scripts examples
	uv run ruff format --check src tests scripts examples

format:  ## Auto-format and fix lint
	uv run ruff check --fix src tests scripts examples
	uv run ruff format src tests scripts examples

typecheck:  ## mypy --strict
	uv run mypy

test:  ## Run tests on the default Python
	uv run pytest

test-all:  ## Run tests on every supported Python (uv downloads missing interpreters)
	@for v in $(PYTHONS); do \
		echo "== Python $$v"; \
		UV_PROJECT_ENVIRONMENT=.venvs/py$$v uv run --quiet --python $$v --no-default-groups --group test pytest -q || exit 1; \
	done

check: lint typecheck test  ## Everything CI's lint + test jobs run
	uv run python scripts/unasync.py --check

build:  ## Build sdist and wheel into dist/
	uv build

clean:  ## Remove build artefacts and caches
	rm -rf dist build .venvs .pytest_cache .mypy_cache .ruff_cache src/*.egg-info
