#!/usr/bin/env bash

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export INBOX_COPILOT_SECRETS_DIR="$PROJECT_ROOT/inbox-copilot/secrets"
export PYTHONPATH="$PROJECT_ROOT/inbox-copilot"

echo "✔ inbox-copilot environment initialized"
