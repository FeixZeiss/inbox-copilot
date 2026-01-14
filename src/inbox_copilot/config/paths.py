import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env once, globally
load_dotenv()

# Project root (independent of current working directory).
PROJECT_ROOT = Path(__file__).resolve().parents[3]

def resolve_dir(env_key: str, default: str) -> Path:
    """
    Resolve a directory path from ENV.
    Relative paths are resolved against PROJECT_ROOT.
    """
    value = os.getenv(env_key, default)
    path = Path(value)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    path.mkdir(parents=True, exist_ok=True)
    return path


SECRETS_DIR = resolve_dir("INBOX_COPILOT_SECRETS_DIR", "secrets")
STATE_DIR   = resolve_dir("INBOX_COPILOT_STATE_DIR", ".state")
LOGS_DIR    = resolve_dir("INBOX_COPILOT_LOGS_DIR", "logs")

STATE_PATH = STATE_DIR / "state.json"
