# scripts/run_once.py
from pathlib import Path
import json

from inbox_copilot.app.run import run_once

def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    state_path = repo_root / ".state" / "state.json"
    logs_dir = repo_root / "logs"

    summary = run_once(
        state_path=state_path,
        logs_dir=logs_dir,
        bootstrap_days=60,
        verbose=True,
    )

    print("[summary]")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
