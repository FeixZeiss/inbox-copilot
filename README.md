# inbox-copilot 

**inbox-copilot** is a local Python tool that analyzes, classifies, and processes your Gmail inbox  
(e.g. job applications, newsletters, security alerts).

The project uses the **Gmail API**, a **rule-based engine**, and a **persistent state** to process emails efficiently and reproducibly.

---

## Features

- OAuth2 authentication with the Gmail API
- Read Gmail messages (metadata / full)
- Rule-based classification system (applications, newsletters, security alerts, etc.)
- Persistent state (last processed timestamp)
- Clean project architecture (CLI scripts, core logic, storage)
- Designed for local execution with Conda or virtual environments

---

## Project Structure

```text
inbox-copilot/
├── scripts/
│   └── run_once.py          # Single processing run
├── src/
│   └── inbox_copilot/
│       ├── gmail/           # Gmail API client
│       ├── rules/           # Rule engine & rules
│       ├── storage/         # Persistent state handling
│       └── ...
├── secrets/
│   ├── credentials.json     # Google OAuth client (DO NOT COMMIT)
│   └── gmail_token.json     # OAuth token (auto-generated)
├── setup.sh                 # Project environment setup
├── .env                     # Optional: API keys etc.
└── README.md
```
## Requirements
- Linux or WSL
- Python 3.10+
- Google Account with GMailAPI enabled
- Conda or virtualenv

## Gmail API Setup
1. Create a Google Cloud project
2. Enable the Gmail API
3. Create an OAuth client (Desktop application)
4. Download credentials.json
5. Place the file here:
```bash
inbox-copilot/secrets/credentials.json
```

⚠️ Never commit credentials.json or gmail_token.json

## OpenAI / ChatGPT API Setup (optional)
If you use features that call OpenAI (e.g. application analysis), you need an API key.
1. Create an API key in your OpenAI account
2. Create and edit a local .env file in the project root (start from the example template):

Create/edit:
```bash
cp .env.example .env
nano .env
```

Add:
```bash
OPENAI_API_KEY="YOUR_OPENAI_API_KEY_HERE"
```

Notes:
- Keep the quotes if your shell/editor adds special characters.
- Never commit .env (should be in .gitignore).
Edit `.env` before your first run.

## Installation
Conda environment (recommended)
```bash
conda create -n inbox-copilot python=3.11
conda activate inbox-copilot
pip install -r requirements.txt
```
Or use the Makefile:
```bash
make setup
```
## Environment Setup

The project relies on environment variables, which are initialized via setup.sh.
```bash
cd inbox-copilot
source setup.sh
```

Expected output:
```text
✔ inbox-copilot environment initialized
INBOX_COPILOT_SECRETS_DIR=.../inbox-copilot/secrets
```

## ▶️ Running the Project
```bash
python scripts/run_once.py
```
Or with Make:
```bash
make run
```

On the first run:
- A browser window opens for OAuth login
- Gmail access must be granted
- gmail_token.json is created automatically

## 🔁 Repeated Runs
- OAuth token is reused automatically
- Processing state is persisted
- Deleted or unavailable messages are skipped safely

## 🧯 Troubleshooting
❌ invalid_grant: Token has been expired or revoked
```bash
rm secrets/gmail_token.json
python scripts/run_once.py
```
➡️ Re-run OAuth authentication

❌ HttpError 404: Requested entity was not found
- The email was deleted or moved
- The error is handled and the message is skipped
- If you suspect state issues, delete `.state/state.json` to force a bootstrap run

## Security
- Secrets are stored locally only
- No cloud backend besides Gmail API
- Tokens can be revoked at any time in Google Account settings

## Future Ideas
- IMAP fallback
- LLM-assisted classification
- Web dashboard

## 🧠 Philosophy
- Inbox Zero — but with control.
- Automation without black boxes. Rules over magic.

## 📄 License
Private / educational project
