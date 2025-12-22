#!/usr/bin/env bash
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Optional: load .env
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  source "$PROJECT_ROOT/.env"
  set +a
fi

# IMPORTANT: secrets dir is directly under the repo root
export INBOX_COPILOT_SECRETS_DIR="$PROJECT_ROOT/secrets"

# Make sure Python can import your package
export PYTHONPATH="$PROJECT_ROOT"

echo "✔ inbox-copilot environment initialized"
echo "  INBOX_COPILOT_SECRETS_DIR=$INBOX_COPILOT_SECRETS_DIR"
