from __future__ import annotations

from inbox_copilot.models import EmailAnalysis
from inbox_copilot.pipeline.policy import actions_from_analysis
from inbox_copilot.rules.core import ActionType


def test_actions_from_analysis_prefers_most_specific_labels() -> None:
    analysis = EmailAnalysis(
        category="job_application",
        suggested_labels=[
            "Applications",
            "Applications/Interview",
            "Interview",
            "Interview/Application",
            "Interview/Application",
        ],
        summary_bullets=[],
        todos=[],
        confidence=0.9,
        notes=[],
        reason="INTERVIEW",
    )

    actions = actions_from_analysis(analysis, message_id="msg-1")
    added_labels = {a.label_name for a in actions if a.type == ActionType.ADD_LABEL}

    assert "Applications" not in added_labels
    assert "Interview" not in added_labels
    assert "Applications/Interview" in added_labels
    assert "Interview/Application" in added_labels
    assert len(added_labels) == 2
