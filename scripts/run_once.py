<<<<<<< HEAD
from pathlib import Path

from inbox_copilot.gmail.client import GmailClient, GmailClientConfig


def main() -> None:
    cfg = GmailClientConfig(
        credentials_path=Path("secrets/credentials.json"),
        token_path=Path("secrets/token.json"),
    )

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
=======
>>>>>>> parent of bdccb5e (Merge branch 'salvage/client-setup')
