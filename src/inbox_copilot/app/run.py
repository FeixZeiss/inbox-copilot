# src/inbox_copilot/app/run.py
from __future__ import annotations

from dataclasses import dataclass, asdict

from email.utils import parseaddr
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
from inbox_copilot.rules.core import ActionType


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
    # Exclude drafts and own-sent messages from labeling runs.
    return f"newer_than:{days}d -in:drafts -from:me"


def _incremental_query(last_internal_date_ms: int) -> str:
    # Gmail "after:" expects seconds since epoch, not milliseconds.
    epoch_seconds = max(0, int(last_internal_date_ms / 1000))
    # Exclude drafts and own-sent messages from labeling runs.
    return f"after:{epoch_seconds} -in:drafts -from:me"


def _normalized_address(value: str) -> str:
    # Parse "Name <mail@domain>" safely and normalize for exact comparisons.
    return parseaddr(value)[1].strip().lower()


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
    # Pull full payload once so we can extract headers + body consistently.
    msg = client.get_message(message_id, fmt="full")
    payload = msg.get("payload", {})
    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

    subject = headers.get("Subject", "")
    from_email = headers.get("From", "")
    snippet = msg.get("snippet", "")
    body_text = extract_body_from_payload(payload)
    internal_date_ms = int(msg.get("internalDate") or 0)
    label_ids = [str(x) for x in (msg.get("labelIds") or [])]

    email = NormalizedEmail(
        message_id=message_id,
        subject=subject,
        from_email=from_email,
        snippet=snippet,
        body_text=body_text,
        internal_date_ms=internal_date_ms,
        headers=headers,
        label_ids=label_ids,
    )
    return email, headers


def process_message(
    client: GmailClient,
    mail: NormalizedEmail,
    executor: ActionExecutor,
    report_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> None:
    # Keep analysis pure and delegate side effects to the executor.
    analysis = analyze_email(mail)
    actions = actions_from_analysis(analysis, message_id=mail.message_id)

    if report_cb:
        for action in actions:
            if action.type == ActionType.ADD_LABEL:
                report_cb(
                    {
                        "message_id": mail.message_id,
                        "from": mail.from_email,
                        "subject": mail.subject,
                        "label": action.label_name,
                    }
                )

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

    def report(
        step: str,
        *,
        detail: str | None = None,
        metrics: Optional[Dict[str, Any]] = None,
        **extra: Any,
    ) -> None:
        if not progress_cb:
            return
        # Normalize the payload shape for both UI and CLI consumers.
        payload: Dict[str, Any] = {"detail": detail}
        if metrics:
            payload["metrics"] = metrics
        if extra:
            payload.update(extra)
        progress_cb(step, payload)

    processed = 0
    skipped_deleted = 0
    errors = 0
    latest_ts: Optional[int] = None
    latest_ids_at_ts: set[str] = set()
    seen = 0
    fetched = 0

    # --- Load state ---
    report("load_state", detail="Loading state")
    st = load_state(state_path)
    already_processed_at_latest_ts = set(st.last_message_ids_at_latest_ts or [])

    logs_dir.mkdir(parents=True, exist_ok=True)

    # --- Gmail client ---
    report("connect_gmail", detail="Connecting to Gmail")
    cfg = load_gmail_config()
    client = GmailClient(cfg)
    client.connect()
    own_email = _normalized_address(client.get_profile().get("emailAddress", ""))
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
        cursor_ms = st.last_internal_date_ms
        # Legacy state migration: if we only have a timestamp (no ID cursor yet),
        # advance one second to avoid repeatedly reprocessing the last message.
        if cursor_ms is not None and not st.last_message_ids_at_latest_ts:
            cursor_ms += 1000
        message_ids = get_message_ids_since(
            client,
            last_internal_date_ms=cursor_ms or 0,
            max_results=max_results,
        )

    fetched = len(message_ids)
    log(f"[run] Found {fetched} messages")
    report(
        "load_messages",
        detail=f"Loading message payloads 0/{fetched}",
        metrics={
            "processed": processed,
            "message_ids_seen": seen,
            "skipped_deleted": skipped_deleted,
            "errors": errors,
        },
    )

    # --- Load messages first, then process in chronological order ---
    loaded_mails: List[NormalizedEmail] = []
    for mid in message_ids:
        mail: Optional[NormalizedEmail] = None
        try:
            mail, _headers = build_mail(client, mid)
            loaded_mails.append(mail)
        except KeyError as exc:
            # Message deleted/moved between list and fetch.
            skipped_deleted += 1
            log(f"[skip] {exc}")
        except Exception as exc:
            errors += 1
            log(f"[error] {type(exc).__name__}: {exc}")
            report(
                "error",
                detail=f"{type(exc).__name__}: {exc}",
                error={
                    "message_id": mid,
                    "from": mail.from_email if mail else "",
                    "subject": mail.subject if mail else "",
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )

    # Oldest first so classification/actions follow timeline order.
    loaded_mails.sort(key=lambda m: (m.internal_date_ms, m.message_id))

    # Build an eligible list first so "Seen" only reflects actually processable mails.
    eligible_mails: List[NormalizedEmail] = []
    for mail in loaded_mails:
        if st.last_internal_date_ms is not None:
            if mail.internal_date_ms < st.last_internal_date_ms:
                continue
            if (
                mail.internal_date_ms == st.last_internal_date_ms
                and mail.message_id in already_processed_at_latest_ts
            ):
                continue
        if "DRAFT" in {lbl.upper() for lbl in mail.label_ids}:
            continue
        from_addr = _normalized_address(mail.from_email)
        if own_email and from_addr == own_email:
            continue
        eligible_mails.append(mail)

    seen = len(eligible_mails)
    to_process = seen
    if to_process:
        log("[run] Processing messages in chronological order (oldest to newest)")
    else:
        log(f"[run] No eligible messages to process (fetched={fetched})")
    report(
        "processing",
        detail=f"Processing 0/{to_process}",
        metrics={
            "processed": processed,
            "message_ids_seen": seen,
            "skipped_deleted": skipped_deleted,
            "errors": errors,
        },
    )

    for index, mail in enumerate(eligible_mails, start=1):
        try:
            process_message(
                client,
                mail,
                executor,
                report_cb=lambda action: report(
                    "action",
                    detail="Label applied",
                    action=action,
                ),
            )
            processed += 1

            ts = getattr(mail, "internal_date_ms", None)
            if ts is not None:
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts
                    latest_ids_at_ts = {mail.message_id}
                elif ts == latest_ts:
                    latest_ids_at_ts.add(mail.message_id)

        except Exception as exc:
            errors += 1
            log(f"[error] {type(exc).__name__}: {exc}")
            report(
                "error",
                detail=f"{type(exc).__name__}: {exc}",
                error={
                    "message_id": mail.message_id,
                    "from": mail.from_email,
                    "subject": mail.subject,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
        finally:
            report(
                "processing",
                detail=f"Processing {index}/{to_process}",
                metrics={
                    "processed": processed,
                    "message_ids_seen": seen,
                    "skipped_deleted": skipped_deleted,
                    "errors": errors,
                },
            )

    # --- Update & persist state ---
    report("save_state", detail="Saving state")
    if latest_ts is not None:
        st.last_internal_date_ms = latest_ts
        st.last_message_ids_at_latest_ts = sorted(latest_ids_at_ts)
    st.runs += 1

    save_state(state_path, st)

    summary = RunSummary(
        processed=processed,
        skipped_deleted=skipped_deleted,
        errors=errors,
        latest_internal_date_ms=latest_ts,
        message_ids_seen=seen,
    )
    report("done", detail="Run completed", metrics=asdict(summary))
    return asdict(summary)
