.PHONY: setup run

setup:
	@echo "Installing Python dependencies..."
	python3 -m pip install -r requirements.txt
	@echo "If you need API keys, create a .env file in the project root."

run:
	python3 scripts/run_once.py
