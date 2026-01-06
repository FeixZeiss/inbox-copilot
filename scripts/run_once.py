import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# State handling: persistent application state (historyId, run counter)
from inbox_copilot.actions.executor import default_executor
from inbox_copilot.storage.state import load_state, save_state

# Gmail API wrapper and config
from inbox_copilot.gmail.client import GmailClient, GmailClientConfig

# Rule system: normalized mail representation + concrete rules
from inbox_copilot.rules.core import MailItem
from inbox_copilot.rules.builtins import GoogleSecurityAlertRule, JobAlertRule, NewsletterRule, NoFitRule

# Adjust this import to where your Action lives
from inbox_copilot.rules.actions import Action  # <-- change if needed
from googleapiclient.errors import HttpError
from inbox_copilot.config.paths import STATE_PATH
from inbox_copilot.config.paths import SECRETS_DIR



def load_gmail_config() -> GmailClientConfig:
    cred = SECRETS_DIR / "credentials.json"
    if not cred.exists():
        raise RuntimeError(
            f"Missing Gmail credentials at {cred}. "
            "Did you configure INBOX_COPILOT_SECRETS_DIR?"
        )
    
    token = SECRETS_DIR / "gmail_token.json"
    if not token.exists():
        raise RuntimeError(
            f"Missing Gmail credentials at {token}. "
            "Did you configure INBOX_COPILOT_SECRETS_DIR?"
        )

    cfg = GmailClientConfig(
        credentials_path=cred,
        token_path=token,
        user_id="me",
    )

    if not cfg.credentials_path.exists():
        raise FileNotFoundError(f"Missing credentials: {cfg.credentials_path}")

    return cfg


def main() -> None:
    # ------------------------------------------------------------------
    # Rule registry
    # ------------------------------------------------------------------
    rules = [
        GoogleSecurityAlertRule(),
        NewsletterRule(),
        JobAlertRule(),
    ]

    # Optional: run higher priority rules first if you add "priority"
    # TODO:evtl anpassen
    rules = sorted(rules, key=lambda r: getattr(r, "priority", 0), reverse=True)

    # ------------------------------------------------------------------
    # Load persistent application state
    # -----------------------------------------------------------------
    st = load_state(STATE_PATH)

    # ------------------------------------------------------------------
    # Initialize Gmail client
    # ------------------------------------------------------------------
    cfg = load_gmail_config()
    client = GmailClient(cfg)
    client.connect()

    profile = client.get_profile()
    print(f"Connected as: {profile.get('emailAddress')}")

    # ------------------------------------------------------------------
    # Local helpers: one evaluation flow for BOTH bootstrap + incremental
    # ------------------------------------------------------------------
    def build_mail(mid: str) -> tuple[MailItem, dict]:
        """Fetch message metadata and normalize into MailItem + headers."""
        msg = client.get_message(mid, fmt="metadata")
        internal_date_ms = int(msg.get("internalDate", 0))
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}

        mail = MailItem(
            id=mid,
            thread_id=msg.get("threadId"),
            headers=headers,
            snippet=msg.get("snippet", ""),
            internal_date_ms=internal_date_ms,
        )
        return mail, headers

    def evaluate_rules(mail: MailItem) -> list[tuple[str, Action]]:
        """Return a list of (rule_name, action) pairs for this mail."""
        planned: list[tuple[str, Action]] = []
        for rule in rules:
            if rule.match(mail):
                for action in rule.actions(mail):
                    planned.append((rule.name, action))
        return planned

    def dedupe_actions(planned: list[tuple[str, Action]]) -> list[tuple[str, Action]]:
        """Remove duplicate actions (same type/label/reason) while keeping order."""
        seen: set[tuple[str, str | None, str]] = set()
        out: list[tuple[str, Action]] = []
        for rule_name, action in planned:
            key = (action.type, action.label_name, action.reason)
            if key not in seen:
                seen.add(key)
                out.append((rule_name, action))
        return out

    def print_dry_run(headers: dict, planned: list[tuple[str, Action]]) -> None:
        """Pretty print planned actions for one mail."""
        if not planned:
            return

        print("----")
        print(f"Subject: {headers.get('Subject', '')}")
        print(f"From:    {headers.get('From', '')}")

        for rule_name, action in planned:
            label = action.label_name or ""
            print(f"[rule:{rule_name}] -> {action.type} {label} ({action.reason})")

    def process_message(mail: MailItem, headers: dict) -> None:
        #try:
        #    mail, headers = build_mail(mid)
        #except KeyError as e:
        #    # Message was deleted/moved between list/history and fetch
        #    print(f"[SKIP] {e}")
        #    return

        best_actions: list[Action] = []
        best_rule_name = "NONE"

        for rule in sorted(rules, key=lambda r: r.priority, reverse=True):
            if rule.match(mail):
                best_actions = list(rule.actions(mail))
                best_rule_name = getattr(rule, "name", rule.__class__.__name__)
                break

        if not best_actions:
            nofit = NoFitRule()
            best_actions = list(nofit.actions(mail))
            best_rule_name = getattr(nofit, "name", nofit.__class__.__name__)

        subj = headers.get("Subject", "")
        frm = headers.get("From", "")
        print(f"[match] {mid} -> {best_rule_name} | Subject={subj!r} | From={frm!r}")

        executor = default_executor(dry_run=False)
        executor.run(client, best_actions)

    def get_message_ids_incremental(start_history_id: str) -> tuple[list[str], str]:
        message_ids: list[str] = []
        page_token: str | None = None
        last_resp: dict | None = None

        while True:
            resp = client.service.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded", "labelAdded"],
                labelId="INBOX",
                pageToken=page_token,
                maxResults=500,
            ).execute()
            last_resp = resp

            for h in resp.get("history", []):
                for added in h.get("messagesAdded", []):
                    message_ids.append(added["message"]["id"])
                for la in h.get("labelsAdded", []):
                    msg = la.get("message")
                    if msg and "id" in msg:
                        message_ids.append(msg["id"])

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        # dedupe in-order
        seen = set()
        message_ids = [mid for mid in message_ids if not (mid in seen or seen.add(mid))]

        # “neuer checkpoint”: am besten aus profile frisch holen (oder last_resp["historyId"] wenn vorhanden)
        latest_profile = client.get_profile()
        new_history_id = latest_profile["historyId"]

        return message_ids, new_history_id


    def get_message_ids_bootstrap(ageMails) -> list[str]:
        return client.list_messages(query=f"in:inbox newer_than:{ageMails}d", max_results=200)

    if st.last_internal_date_ms is None:
        ageMails = 60
        print(f"[bootstrap] No last_internal_date_ms, fetching messages from last {ageMails} days")
        message_ids = get_message_ids_bootstrap(ageMails)
        print(f"[bootstrap] Found {len(message_ids)} messages in last 7 days")
        
        latest_ts = 0
        for mid in message_ids:
            try:
                mail, headers = build_mail(mid)
            except KeyError as e:
                # Message was deleted/moved between list/history and fetch
                print(f"[SKIP] {e}")
                continue
            
            process_message(mail, headers)
            ts = mail.internal_date_ms
            latest_ts = max(latest_ts, ts)
            print(f"mid={mid} internal_date_ms={mail.internal_date_ms}, latest_ts={latest_ts}  ")

        st.last_internal_date_ms = latest_ts
        st.runs += 1
        save_state(STATE_PATH, st)
        return

    # -------------------------
    # incremental (time-based)
    # -------------------------
    last_ms = int(st.last_internal_date_ms or 0)

    # Gmail query uses seconds, not ms. Add safety buffer to avoid missing messages in the same second.
    after_seconds = max(0, (last_ms // 1000) - 60)

    query = f"in:inbox after:{after_seconds}"
    print(f"[incremental] Query={query}")

    message_ids = client.list_messages(query=query, max_results=500)
    print(f"[incremental] Found {len(message_ids)} candidate messages")

    latest_ts = last_ms

    for mid in message_ids:
        try:
            mail, headers = build_mail(mid)
        except KeyError as e:
            print(f"[SKIP] {e}")
            continue

        # Dedupe/guard: only process messages strictly newer than our last stored ms timestamp
        if mail.internal_date_ms <= last_ms:
            # likely re-fetched due to buffer / second-resolution of after:
            continue

        process_message(mail, headers)
        latest_ts = max(latest_ts, mail.internal_date_ms)
        print("processed message", mid, "internal_date_ms=", mail.internal_date_ms, "latest_ts=", latest_ts)

    # Update state only if we actually saw something newer
    st.last_internal_date_ms = latest_ts
    st.runs += 1
    save_state(STATE_PATH, st)

    print(f"[state] runs={st.runs} last_internal_date_ms={st.last_internal_date_ms}")

if __name__ == "__main__":
    main()
