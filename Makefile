.PHONY: setup setup-dev run lint test check

setup:
	@echo "Installing Python dependencies..."
	python3 -m pip install -r requirements.txt
	@if [ ! -f .env ]; then \
		echo "Creating .env from .env.example"; \
		cp .env.example .env; \
	fi
	@if [ ! -f secrets/credentials.json ]; then \
		echo "Missing secrets/credentials.json (Gmail OAuth client). See README.md for setup."; \
	fi
	@echo "If you need API keys, edit .env in the project root."

setup-dev: setup
	@echo "Installing dev tooling (ruff + pytest)..."
	python3 -m pip install -e ".[dev]"
	@echo "Installing frontend dependencies..."
	npm --prefix frontend install

run:
	@bash -c "source setup.sh && python3 scripts/run_once.py"

lint:
	python3 -m ruff check backend src scripts tests
	npm --prefix frontend run lint

test:
	python3 -m pytest -q

check: lint test
