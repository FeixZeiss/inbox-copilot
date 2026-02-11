from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from inbox_copilot.rules.rules import GoogleSecurityAlertRule, JobAlertRule, NewsletterRule


@dataclass(frozen=True)
class RuleResult:
    category: str
    labels: List[str]
    confidence: float
    notes: List[str]
    reason: str | None = None


def classify_email(*, subject: str, from_email: str, body_text: str) -> RuleResult:
    """
    Lightweight classification using the rule engine.
    Returns a neutral result that can be turned into actions by a policy layer.
    """
    # Build a minimal MailItem-like object for the rules.
    mail = _make_mail_item(subject=subject, from_email=from_email, body_text=body_text)

    rules = [
        GoogleSecurityAlertRule(),
        NewsletterRule(),
        JobAlertRule(),
    ]
    # Higher priority rules win when multiple could match.
    rules = sorted(rules, key=lambda r: r.priority, reverse=True)

    for rule in rules:
        matched, reason = rule.match(mail)
        if matched:
            return _result_from_rule(rule.name, reason)

    return RuleResult(
        category="no_fit",
        labels=[],
        confidence=0.2,
        notes=["No rule matched"],
        reason=None,
    )


def _result_from_rule(rule_name: str, reason: str) -> RuleResult:
    if rule_name == "google_security_alert":
        return RuleResult(
            category="security",
            labels=["Security"],
            confidence=0.9,
            notes=[f"Matched rule: {rule_name}"],
            reason=reason,
        )
    if rule_name == "newsletter":
        return RuleResult(
            category="newsletter",
            labels=["Newsletter"],
            confidence=0.7,
            notes=[f"Matched rule: {rule_name}"],
            reason=reason,
        )
    if rule_name == "job_application":
        label_suffix = _job_label_suffix(reason)
        return RuleResult(
            category="job_application",
            labels=["Applications", f"Applications/{label_suffix}"],
            confidence=0.85,
            notes=[f"Matched rule: {rule_name} ({reason})"],
            reason=reason,
        )

    return RuleResult(
        category="no_fit",
        labels=[],
        confidence=0.2,
        notes=[f"Unknown rule: {rule_name}"],
        reason=reason,
    )


def _job_label_suffix(reason: str) -> str:
    # Map fine-grained reasons into a Gmail label hierarchy.
    mapping = {
        JobAlertRule.CONFIRM_REASON: "Confirmation",
        JobAlertRule.INTERVIEW_REASON: "Interview",
        JobAlertRule.REJECT_REASON: "Rejection",
        JobAlertRule.NOFIT_REASON: "NoFit",
    }
    return mapping.get(reason, reason or "Unknown")


def _make_mail_item(*, subject: str, from_email: str, body_text: str):
    # Import locally to avoid dependency cycles in type checking.
    from inbox_copilot.rules.core import MailItem

    return MailItem(
        id="analysis-only",
        thread_id=None,
        headers={"Subject": subject, "From": from_email},
        snippet=body_text,
        internal_date_ms=0,
    )
