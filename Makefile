.PHONY: sync lint format typecheck test check pack

sync:
	uv sync --locked --python 3.14.10

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

typecheck:
	uv run pyright

test:
	uv run pytest

check: lint typecheck test

pack:
	uv run python scripts/build_plugin.py
