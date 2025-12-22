from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from inbox_copilot.rules.core import Action, ActionType
from inbox_copilot.actions.handlers import (
    ActionHandler,
    PrintHandler,
    AddLabelHandler,
    ArchiveHandler,
)
from inbox_copilot.gmail.client import GmailClient


@dataclass
class ActionExecutor:
    handlers: Dict[ActionType, ActionHandler]
    dry_run: bool = False
    continue_on_error: bool = True

    def run(self, client: GmailClient, actions: list[Action]) -> None:
        for action in actions:
            handler = self.handlers.get(action.type)
            if not handler:
                print(f"[WARN] No handler registered for action type: {action.type}")
                continue

            if self.dry_run:
                print(
                    f"[DRY-RUN] would run type={action.type} "
                    f"message_id={action.message_id} label={action.label_name} reason={action.reason}"
                )
                continue

            try:
                handler.handle(client, action)
            except Exception as e:
                print(
                    f"[ERROR] Action failed type={action.type} message_id={action.message_id} "
                    f"reason={action.reason} err={e}"
                )
                if not self.continue_on_error:
                    raise


def default_executor(*, dry_run: bool = False) -> ActionExecutor:
    return ActionExecutor(
        handlers={
            ActionType.PRINT: PrintHandler(),
            ActionType.ADD_LABEL: AddLabelHandler(),
            ActionType.ARCHIVE: ArchiveHandler(),
        },
        dry_run=dry_run,
    )
