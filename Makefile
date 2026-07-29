.PHONY: check docs test lint smoke

check: lint docs test smoke

lint:
	uv run --cache-dir .uv-cache ruff check .

docs:
	python3 scripts/check_docs.py

test:
	uv run --cache-dir .uv-cache pytest -q

smoke:
	uv run --cache-dir .uv-cache --with pyyaml --with requests python scripts/hermes_smoke.py
