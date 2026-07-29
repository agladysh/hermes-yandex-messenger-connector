.PHONY: check test lint smoke

check: lint test smoke

lint:
	uv run --cache-dir .uv-cache ruff check .

test:
	uv run --cache-dir .uv-cache pytest -q

smoke:
	uv run --cache-dir .uv-cache --with pyyaml --with requests python scripts/hermes_smoke.py
