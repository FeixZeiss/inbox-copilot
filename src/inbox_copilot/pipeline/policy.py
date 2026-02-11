from __future__ import annotations

from typing import List

from inbox_copilot.models import EmailAnalysis
from inbox_copilot.rules.core import Action, ActionType


def actions_from_analysis(analysis: EmailAnalysis, message_id: str) -> List[Action]:
    # Policy layer decides side effects based on analysis output.
    actions: List[Action] = []

    for label in sorted(set(analysis.suggested_labels)):
        if not label:
            continue
        actions.append(
            Action(
                type=ActionType.ADD_LABEL,
                message_id=message_id,
                label_name=label,
                reason=analysis.reason or analysis.category,
            )
        )

    if analysis.category == "job_application":
        actions.append(
            Action(
                type=ActionType.ANALYZE_APPLICATION,
                message_id=message_id,
                reason=analysis.reason or "Job application detected",
            )
        )

    return actions
