#!/usr/bin/env bash
set -e

if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "Environment loaded for inbox-copilot"
