from __future__ import annotations
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

@dataclass
class AppState:
    # Placeholder for Gmail History API tracking (not used yet).
    last_history_time: Optional[str] = None
    last_internal_date_ms: Optional[int] = None
    # Message IDs already processed at the latest timestamp (same-second dedupe cursor).
    last_message_ids_at_latest_ts: list[str] = field(default_factory=list)
    runs: int = 0

def load_state(path: Path) -> AppState:
    if not path.exists():
        return AppState()
    data = json.loads(path.read_text(encoding="utf-8"))
    # Keep load resilient to legacy/extra fields.
    return AppState(
        # Backward compatibility: keep reading the legacy key if present.
        last_history_time=data.get("last_history_time") or data.get("last_history_TIME"),
        last_internal_date_ms=data.get("last_internal_date_ms"),
        last_message_ids_at_latest_ts=list(data.get("last_message_ids_at_latest_ts") or []),
        runs=int(data.get("runs") or 0),
    )

def save_state(path: Path, state: AppState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
