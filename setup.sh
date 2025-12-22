#!/usr/bin/env bash

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Optional: load .env for OPENAI_API_KEY etc.
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  source "$PROJECT_ROOT/.env"
  set +a
fi

export INBOX_COPILOT_SECRETS_DIR="$PROJECT_ROOT/secrets"
export PYTHONPATH="$PROJECT_ROOT"

echo "✔ inbox-copilot environment initialized"
echo "  INBOX_COPILOT_SECRETS_DIR=$INBOX_COPILOT_SECRETS_DIR"
