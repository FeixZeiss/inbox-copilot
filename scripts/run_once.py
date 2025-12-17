from pathlib import Path
import os

from inbox_copilot.gmail.client import GmailClient, GmailClientConfig

def load_gmail_config() -> GmailClientConfig:
    secrets_dir = os.getenv("INBOX_COPILOT_SECRETS_DIR") or os.getenv("AIVA_SECRETS_DIR")
    if not secrets_dir:
        raise RuntimeError("Set INBOX_COPILOT_SECRETS_DIR (or AIVA_SECRETS_DIR).")

    base = Path(secrets_dir)

    cfg = GmailClientConfig(
        credentials_path=base / "credentials.json",
        token_path=base / "gmail_token.json",
        user_id="me",
    )

    if not cfg.credentials_path.exists():
        raise FileNotFoundError(f"Missing credentials: {cfg.credentials_path}")

    cfg.token_path.parent.mkdir(parents=True, exist_ok=True)
    return cfg

def main() -> None:
    cfg = load_gmail_config()

    client = GmailClient(cfg)
    client.connect()

    profile = client.get_profile()
    print(f"Connected as: {profile.get('emailAddress')}")

    ids = client.list_messages(query="in:inbox newer_than:7d", max_results=5)
    print(f"Found {len(ids)} messages")

    for mid in ids:
        msg = client.get_message(mid, fmt="metadata")
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        print("----")
        print(f"Subject: {headers.get('Subject')}")
        print(f"From:    {headers.get('From')}")


if __name__ == "__main__":
    main()
