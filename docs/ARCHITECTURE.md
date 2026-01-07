ARCHITECTURE OVERVIEW
=====================

This document describes the main classes/modules and how `run_once.py` works.


Key Classes and Modules
-----------------------

Rules and Actions
- `inbox_copilot.rules.core.MailItem`
  - Lightweight, rule-oriented representation of an email.
  - Used by the rules for matching.
- `inbox_copilot.rules.core.ActionType`
  - Enum of supported actions (add label, archive, analyze, etc.).
- `inbox_copilot.rules.core.Action`
  - Action payload (type, message_id, label_name, reason).
- `inbox_copilot.rules.BaseRule.BaseRule`
  - Base class for rules. `match()` returns `(matched, reason)`.
  - `actions()` yields `Action` objects when a rule matches.
- `inbox_copilot.rules.rules.*Rule`
  - Concrete rules (security, newsletter, job application, no-fit).

Analysis Pipeline
- `inbox_copilot.models.NormalizedEmail`
  - Canonical, analysis-friendly email shape (subject, from, body, headers).
- `inbox_copilot.models.EmailAnalysis`
  - Neutral analysis result (category, labels, summary, todos, confidence).
- `inbox_copilot.rules.classification.classify_email`
  - Runs the rule engine to produce a neutral `RuleResult`.
- `inbox_copilot.pipeline.orchestrator.analyze_email`
  - Calls `classify_email`, `summarize`, and `extract_todos`.
  - Produces a single `EmailAnalysis`.
- `inbox_copilot.pipeline.policy.actions_from_analysis`
  - Policy layer that turns `EmailAnalysis` into concrete `Action` objects.

Extraction and Parsing
- `inbox_copilot.parsing.parser.extract_body_from_payload`
  - Parses Gmail API payload to a plain-text body (or HTML fallback).
- `inbox_copilot.extractors.summary.summarize`
  - Lightweight summary bullets.
- `inbox_copilot.extractors.todos.extract_todos`
  - Heuristic action-item extraction.

Execution
- `inbox_copilot.actions.executor.ActionExecutor`
  - Executes `Action` objects using handlers.
- `inbox_copilot.actions.handlers.*Handler`
  - Implements actual behavior (label, archive, print, analyze).
- `inbox_copilot.gmail.client.GmailClient`
  - Wraps Gmail API calls and label management.
- `inbox_copilot.storage.state.AppState`
  - Persists last processed timestamp and run counter.


How `scripts/run_once.py` Works
-------------------------------

High-level flow:
1) Load app state (last processed timestamp).
2) Create and connect `GmailClient`.
3) Fetch message IDs (bootstrap or incremental).
4) For each message:
   - Fetch full Gmail payload.
   - Build `NormalizedEmail`.
   - Run `analyze_email` (orchestrator).
   - Convert analysis -> actions via `actions_from_analysis`.
   - Execute actions with `ActionExecutor`.
5) Update state with the newest message timestamp.

Key functions in `run_once.py`:
- `load_gmail_config()`:
  - Resolves credential/token paths and returns `GmailClientConfig`.
- `build_email(mid)`:
  - Fetches Gmail message (full).
  - Extracts headers + body via `extract_body_from_payload`.
  - Returns a `NormalizedEmail` plus raw headers.
- `process_message(email, headers)`:
  - Calls `analyze_email(email)` to get `EmailAnalysis`.
  - Calls `actions_from_analysis(...)` to get `Action` objects.
  - Runs actions with `ActionExecutor`.

Bootstrap vs. incremental:
- Bootstrap: if no `last_internal_date_ms` is stored, fetch a recent window
  (`newer_than:60d`) and process all.
- Incremental: query Gmail using `after:<timestamp>` and only process
  messages newer than the stored timestamp.

Where to change behavior:
- Classification logic: `src/inbox_copilot/rules/rules.py`
- Orchestrator outputs: `src/inbox_copilot/pipeline/orchestrator.py`
- Policy decisions: `src/inbox_copilot/pipeline/policy.py`
