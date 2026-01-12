# backend/app/api/run.py
from pathlib import Path
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

    def progress_cb(step: str, payload: dict) -> None:
        detail = payload.get("detail")
        update_fields = {
            "state": "running",
            "step": step,
            "detail": detail,
        }
        if "metrics" in payload:
            update_fields["metrics"] = payload.get("metrics") or {}
        run_status_store.update(**update_fields)

    try:
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
