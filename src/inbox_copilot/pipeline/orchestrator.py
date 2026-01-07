from inbox_copilot.models import NormalizedEmail, EmailAnalysis
from inbox_copilot.rules.classification import classify_email
from inbox_copilot.extractors.todos import extract_todos
from inbox_copilot.extractors.summary import summarize

def analyze_email(email: NormalizedEmail) -> EmailAnalysis:
    rule_result = classify_email(
        subject=email.subject,
        from_email=email.from_email,
        body_text=email.body_text,
    )

    todos = extract_todos(email.subject, email.body_text)
    summary_bullets = summarize(email.snippet, email.body_text)

    notes = list(rule_result.notes)
    if todos:
        notes.append("Detected potential action items")

    return EmailAnalysis(
        category=rule_result.category,
        suggested_labels=rule_result.labels,
        summary_bullets=summary_bullets,
        todos=todos,
        confidence=rule_result.confidence,
        notes=notes,
        reason=rule_result.reason,
    )
