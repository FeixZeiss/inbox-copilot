from __future__ import annotations

from typing import List

from inbox_copilot.models import EmailAnalysis
from inbox_copilot.rules.core import Action, ActionType


def _prefer_most_specific_labels(labels: List[str]) -> List[str]:
    # If both parent and child labels are present, keep only the child label.
    unique = sorted({label.strip() for label in labels if label and label.strip()})
    if not unique:
        return []

    unique_set = set(unique)
    filtered: List[str] = []
    for label in unique:
        prefix = f"{label}/"
        has_child = any(
            other != label and other.startswith(prefix) for other in unique_set
        )
        if not has_child:
            filtered.append(label)
    return filtered


def actions_from_analysis(analysis: EmailAnalysis, message_id: str) -> List[Action]:
    # Policy layer decides side effects based on analysis output.
    actions: List[Action] = []

    for label in _prefer_most_specific_labels(analysis.suggested_labels):
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
