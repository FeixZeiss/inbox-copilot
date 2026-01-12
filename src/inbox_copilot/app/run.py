# src/inbox_copilot/app/run.py
from __future__ import annotations

from dataclasses import dataclass, asdict

from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable

from inbox_copilot.actions.executor import ActionExecutor, default_executor
from inbox_copilot.config.paths import SECRETS_DIR
from inbox_copilot.gmail.client import GmailClient, GmailClientConfig
from inbox_copilot.models import NormalizedEmail
from inbox_copilot.parsing.parser import extract_body_from_payload
from inbox_copilot.pipeline.orchestrator import analyze_email
from inbox_copilot.pipeline.policy import actions_from_analysis
from inbox_copilot.storage.state import load_state, save_state

@dataclass
class RunSummary:
    processed: int
    skipped_deleted: int
    errors: int
    latest_internal_date_ms: Optional[int]
    message_ids_seen: int


def load_gmail_config() -> GmailClientConfig:
    credentials_path = SECRETS_DIR / "credentials.json"
    if not credentials_path.exists():
        raise RuntimeError(
            f"Missing Gmail credentials at {credentials_path}. "
            "Did you configure INBOX_COPILOT_SECRETS_DIR?"
        )

    token_path = SECRETS_DIR / "gmail_token.json"
    return GmailClientConfig(
        credentials_path=credentials_path,
        token_path=token_path,
        user_id="me",
    )


def _bootstrap_query(days: int) -> str:
    return f"newer_than:{days}d"


def _incremental_query(last_internal_date_ms: int) -> str:
    epoch_seconds = max(0, int(last_internal_date_ms / 1000))
    return f"after:{epoch_seconds}"


def get_message_ids_bootstrap(
    client: GmailClient, *, bootstrap_days: int, max_results: int
) -> List[str]:
    query = _bootstrap_query(bootstrap_days)
    return client.list_messages(query=query, max_results=max_results)


def get_message_ids_since(
    client: GmailClient, *, last_internal_date_ms: int, max_results: int
) -> List[str]:
    query = _incremental_query(last_internal_date_ms)
    return client.list_messages(query=query, max_results=max_results)


def build_mail(client: GmailClient, message_id: str) -> Tuple[NormalizedEmail, Dict[str, str]]:
    msg = client.get_message(message_id, fmt="full")
    payload = msg.get("payload", {})
    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

    subject = headers.get("Subject", "")
    from_email = headers.get("From", "")
    snippet = msg.get("snippet", "")
    body_text = extract_body_from_payload(payload)
    internal_date_ms = int(msg.get("internalDate") or 0)

    email = NormalizedEmail(
        message_id=message_id,
        subject=subject,
        from_email=from_email,
        snippet=snippet,
        body_text=body_text,
        internal_date_ms=internal_date_ms,
        headers=headers,
    )
    return email, headers


def process_message(
    client: GmailClient,
    mail: NormalizedEmail,
    executor: ActionExecutor,
) -> None:
    analysis = analyze_email(mail)
    actions = actions_from_analysis(analysis, message_id=mail.message_id)
    executor.run(client, actions)


def run_once(
    *,
    state_path: Path,
    logs_dir: Path,
    bootstrap_days: int = 60,
    max_results: int = 500,
    verbose: bool = False,
    progress_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    Execute a single processing run and return a machine-readable summary.

    Args:
        state_path: Path to persisted state (e.g. .state/state.json).
        logs_dir: Base directory for logs/results (e.g. logs/).
        bootstrap_days: How many days to scan on first run.
        verbose: If True, print progress (English) for CLI usage.

    Returns:
        dict summary (JSON-serializable).
    """
    # NOTE: Keep prints optional and in English (per your preference).
    def log(msg: str) -> None:
        if verbose:
            print(msg)

    def report(step: str, *, detail: str | None = None, **metrics: Any) -> None:
        if not progress_cb:
            return
        payload = {"detail": detail, "metrics": metrics} if metrics else {"detail": detail}
        progress_cb(step, payload)

    processed = 0
    skipped_deleted = 0
    errors = 0
    latest_ts: Optional[int] = None
    seen = 0

    # --- Load state ---
    report("load_state", detail="Loading state")
    st = load_state(state_path)

    logs_dir.mkdir(parents=True, exist_ok=True)

    # --- Gmail client ---
    report("connect_gmail", detail="Connecting to Gmail")
    cfg = load_gmail_config()
    client = GmailClient(cfg)
    client.connect()
    executor = default_executor(dry_run=False)

    # --- Decide bootstrap vs incremental ---
    if st.last_internal_date_ms is None:
        log(f"[bootstrap] No last_internal_date_ms, fetching messages from last {bootstrap_days} days")
        report("fetch_messages", detail="Fetching messages (bootstrap)")
        message_ids = get_message_ids_bootstrap(
            client,
            bootstrap_days=bootstrap_days,
            max_results=max_results,
        )
    else:
        report("fetch_messages", detail="Fetching messages (incremental)")
        message_ids = get_message_ids_since(
            client,
            last_internal_date_ms=st.last_internal_date_ms,
            max_results=max_results,
        )

    seen = len(message_ids)
    log(f"[run] Found {seen} messages")
    report(
        "processing",
        detail=f"Processing 0/{seen}",
        processed=processed,
        message_ids_seen=seen,
        skipped_deleted=skipped_deleted,
        errors=errors,
    )

    # --- Process loop ---
    for mid in message_ids:
        try:
            mail, _headers = build_mail(client, mid)
            process_message(client, mail, executor)
            processed += 1

            ts = getattr(mail, "internal_date_ms", None)
            if ts is not None:
                latest_ts = ts if latest_ts is None else max(latest_ts, ts)

        except KeyError as e:
            # Message deleted/moved between list and fetch
            skipped_deleted += 1
            log(f"[skip] {e}")
            continue
        except Exception as e:
            errors += 1
            log(f"[error] {type(e).__name__}: {e}")
            continue
        finally:
            report(
                "processing",
                detail=f"Processing {processed}/{seen}",
                processed=processed,
                message_ids_seen=seen,
                skipped_deleted=skipped_deleted,
                errors=errors,
            )

    # --- Update & persist state ---
    report("save_state", detail="Saving state")
    if latest_ts is not None:
        st.last_internal_date_ms = latest_ts
    st.runs += 1

    save_state(state_path, st)

    summary = RunSummary(
        processed=processed,
        skipped_deleted=skipped_deleted,
        errors=errors,
        latest_internal_date_ms=latest_ts,
        message_ids_seen=seen,
    )
    report("done", detail="Run completed", **asdict(summary))
    return asdict(summary)
