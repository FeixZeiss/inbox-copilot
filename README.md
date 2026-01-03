# inbox-copilot 📬🤖

**inbox-copilot** ist ein lokales Python-Tool, das dein Gmail-Postfach analysiert, klassifiziert und automatisiert verarbeitet  
(z. B. Bewerbungen, Newsletter, Sicherheitswarnungen).

Das Projekt nutzt die **Gmail API**, ein **regelbasiertes System** und einen **persistenten State**, um Mails effizient und reproduzierbar auszuwerten.

---

## ✨ Features

- 🔐 OAuth2-Authentifizierung mit der Gmail API
- 📥 Lesen von Gmail-Nachrichten (Metadata / Full)
- 🧠 Regelbasiertes Klassifikationssystem (z. B. Bewerbungen, Newsletter, Security Alerts)
- 💾 Persistenter State (z. B. historyId, letzte Runs)
- 🧪 Saubere Projektstruktur (CLI-Skripte, Core-Logik, Storage)
- 🐍 Entwickelt für lokale Nutzung mit Conda / venv

---

## 📁 Projektstruktur

```text
inbox-copilot/
├── scripts/
│   └── run_once.py          # Einmaliger Verarbeitungslauf
├── src/
│   └── inbox_copilot/
│       ├── gmail/           # Gmail API Client
│       ├── rules/           # Regel-Engine & Regeln
│       ├── storage/         # Persistenter State
│       └── ...
├── secrets/
│   ├── credentials.json     # Google OAuth Client (NICHT committen)
│   └── gmail_token.json     # OAuth Token (wird automatisch erzeugt)
├── setup.sh                 # Projekt-Environment Setup
├── .env                     # Optional: API Keys etc.
└── README.md
