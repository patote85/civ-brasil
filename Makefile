ifneq ($(wildcard /workspace/civbr-dados/cache-uv),)
export UV_CACHE_DIR := /workspace/civbr-dados/cache-uv
export UV_OFFLINE := 1
export UV_PYTHON := /usr/bin/python3
export npm_config_cache := /workspace/civbr-dados/cache-npm
export npm_config_offline := true
endif
ifneq ($(wildcard /workspace/civbr-dados/raw),)
export CIVBR_RAW ?= /workspace/civbr-dados/raw
endif

.PHONY: setup lint typecheck test check data-sp web-build verify

setup:
	@if [ ! -f uv.lock ]; then uv lock; fi
	uv sync --dev --locked
	@if [ ! -f web/package-lock.json ]; then npm --prefix web install; else npm --prefix web ci; fi

lint:
	uv run ruff check pipeline tests
	uv run lint-imports
	npm --prefix web run lint

typecheck:
	uv run mypy --strict pipeline tests
	npm --prefix web run typecheck

test:
	uv run pytest
	npm --prefix web run test

check: lint typecheck test

data-sp:
	uv run python -m pipeline.grid.sp

web-build:
	npm --prefix web run build

verify:
	uv run python -m pipeline.verify
