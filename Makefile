.PHONY: setup run

setup:
	@echo "Installing Python dependencies..."
	python3 -m pip install -r requirements.txt
	@if [ ! -f .env ]; then \
		echo "Creating .env from .env.example"; \
		cp .env.example .env; \
	fi
	@echo "If you need API keys, edit .env in the project root."

run:
	python3 scripts/run_once.py
