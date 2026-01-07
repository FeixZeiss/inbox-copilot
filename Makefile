.PHONY: setup run

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

run:
	@bash -c "source setup.sh && python3 scripts/run_once.py"
