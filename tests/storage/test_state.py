from __future__ import annotations

import json
from pathlib import Path

from inbox_copilot.storage.state import load_state, save_state


def test_load_state_supports_legacy_history_key(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "last_history_TIME": "legacy-key-value",
                "last_internal_date_ms": 123,
                "last_message_ids_at_latest_ts": ["m1"],
                "runs": 2,
            }
        ),
        encoding="utf-8",
    )

    state = load_state(state_path)

    assert state.last_history_time == "legacy-key-value"
    assert state.last_internal_date_ms == 123
    assert state.last_message_ids_at_latest_ts == ["m1"]
    assert state.runs == 2


def test_save_state_writes_normalized_history_key(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = load_state(state_path)
    state.last_history_time = "new-key-value"

    save_state(state_path, state)
    payload = json.loads(state_path.read_text(encoding="utf-8"))

    assert payload.get("last_history_time") == "new-key-value"
    assert "last_history_TIME" not in payload
