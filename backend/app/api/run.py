# backend/app/api/run.py
from pathlib import Path
from typing import Any
from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from inbox_copilot.app.run import run_once
from backend.app.status import run_status_store

router = APIRouter()

@router.post("/run")
async def run_endpoint() -> dict:
    repo_root = Path(__file__).resolve().parents[3]  # adjust if needed
    state_path = repo_root / ".state" / "state.json"
    logs_dir = repo_root / "logs"

    run_status_store.update(state="running", step="starting", detail="Starting run", metrics={})

    def progress_cb(step: str, event: dict[str, Any]) -> None:
        detail = event.get("detail")
        status_update = {
            "state": "running",
            "step": step,
            "detail": detail,
        }

        action = event.get("action")
        if action:
            current = run_status_store.snapshot().get("recent_actions", [])
            # Keep newest actions first and cap memory/response size.
            updated = [action] + current
            status_update["recent_actions"] = updated[:50]

        error = event.get("error")
        if error:
            current = run_status_store.snapshot().get("recent_errors", [])
            # Keep most recent errors first, max 50 entries.
            updated = [error] + current
            status_update["recent_errors"] = updated[:50]

        if "metrics" in event:
            status_update["metrics"] = event.get("metrics") or {}
        run_status_store.update(**status_update)

    try:
        # Run blocking Gmail processing in a worker thread so FastAPI stays responsive.
        summary = await run_in_threadpool(
            run_once,
            state_path=state_path,
            logs_dir=logs_dir,
            bootstrap_days=60,
            verbose=False,
            progress_cb=progress_cb,
        )
    except Exception as exc:
        run_status_store.update(state="error", step="error", detail=str(exc))
        raise

    run_status_store.update(
        state="done",
        step="done",
        detail="Run completed",
        summary=summary,
        metrics={
            "processed": summary.get("processed"),
            "message_ids_seen": summary.get("message_ids_seen"),
            "skipped_deleted": summary.get("skipped_deleted"),
            "errors": summary.get("errors"),
        },
    )
    return {"ok": True, "summary": summary}


@router.get("/run/status")
async def run_status() -> dict:
    return {"ok": True, "status": run_status_store.snapshot()}
