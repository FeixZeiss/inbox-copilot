from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import time
from typing import Any, Dict, Optional, List


@dataclass
class RunStatus:
    state: str = "idle"
    step: str = "idle"
    detail: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    summary: Optional[Dict[str, Any]] = None
    recent_actions: List[Dict[str, Any]] = field(default_factory=list)
    # Keep a small rolling window of recent errors for UI visibility.
    recent_errors: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: float = field(default_factory=time)


class RunStatusStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._status = RunStatus()

    def update(self, **fields: Any) -> None:
        # Lock ensures UI polling sees consistent snapshots across threads.
        with self._lock:
            for key, value in fields.items():
                if hasattr(self._status, key):
                    setattr(self._status, key, value)
            self._status.updated_at = time()

    def snapshot(self) -> Dict[str, Any]:
        # Return a copy to avoid mutation by callers.
        with self._lock:
            return {
                "state": self._status.state,
                "step": self._status.step,
                "detail": self._status.detail,
                "metrics": dict(self._status.metrics),
                "summary": self._status.summary,
                "recent_actions": list(self._status.recent_actions),
                "recent_errors": list(self._status.recent_errors),
                "updated_at": self._status.updated_at,
            }


run_status_store = RunStatusStore()
