from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

@dataclass
class AppState:
    # Placeholder for Gmail History API tracking (not used yet).
    last_history_TIME: Optional[str] = None
    last_internal_date_ms: Optional[int] = None
    runs: int = 0

def load_state(path: Path) -> AppState:
    if not path.exists():
        return AppState()
    data = json.loads(path.read_text(encoding="utf-8"))
    return AppState(**data)

def save_state(path: Path, state: AppState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
