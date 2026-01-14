from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, Request
from fastapi.responses import HTMLResponse
from google_auth_oauthlib.flow import InstalledAppFlow

from inbox_copilot.config.paths import SECRETS_DIR
from inbox_copilot.gmail.client import SCOPES
from inbox_copilot.app.run import load_gmail_config
from backend.app.status import run_status_store

router = APIRouter()
_oauth_flows: dict[str, InstalledAppFlow] = {}


@router.get("/secrets/status")
def secrets_status() -> dict:
    credentials_path = SECRETS_DIR / "credentials.json"
    token_path = SECRETS_DIR / "gmail_token.json"
    return {
        "ok": True,
        "secrets_dir": str(SECRETS_DIR),
        "credentials_present": credentials_path.exists(),
        "token_present": token_path.exists(),
    }


@router.post("/secrets/credentials")
def upload_credentials(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Please upload a JSON file.")

    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    target = SECRETS_DIR / "credentials.json"
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload.")

    target.write_bytes(content)
    return {"ok": True, "path": str(target)}


@router.post("/secrets/token")
def upload_token(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Please upload a JSON file.")

    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    target = SECRETS_DIR / "gmail_token.json"
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload.")

    target.write_bytes(content)
    return {"ok": True, "path": str(target)}


@router.post("/secrets/oauth")
def start_oauth(request: Request) -> dict:
    try:
        cfg = load_gmail_config()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    flow = InstalledAppFlow.from_client_secrets_file(
        str(cfg.credentials_path),
        SCOPES,
    )
    # Base URL is used to build the OAuth callback URL dynamically.
    base_url = str(request.base_url).rstrip("/")
    flow.redirect_uri = f"{base_url}/api/secrets/oauth/callback"

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    # Store flow by state so callback can resume securely.
    _oauth_flows[state] = flow
    run_status_store.update(
        state="running",
        step="oauth",
        detail="Waiting for Google login",
    )
    return {"ok": True, "auth_url": auth_url}


@router.get("/secrets/oauth/callback")
def oauth_callback(request: Request, state: str, code: str) -> HTMLResponse:
    flow = _oauth_flows.pop(state, None)
    if not flow:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(load_gmail_config().credentials_path),
            SCOPES,
            state=state,
        )
        base_url = str(request.base_url).rstrip("/")
        flow.redirect_uri = f"{base_url}/api/secrets/oauth/callback"

    try:
        flow.fetch_token(authorization_response=str(request.url))
    except Exception as exc:
        run_status_store.update(state="error", step="oauth", detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cfg = load_gmail_config()
    cfg.token_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.token_path.write_text(flow.credentials.to_json(), encoding="utf-8")

    run_status_store.update(state="done", step="oauth", detail="Gmail OAuth completed")
    return HTMLResponse(
        "<h2>OAuth abgeschlossen</h2><p>Du kannst dieses Fenster schließen.</p>"
    )
