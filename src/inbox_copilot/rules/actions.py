
class Action:
    """Result of a rule match. Can be extended later (e.g., confidence, extracted entities)."""
    type: str
    label_name: str | None = None
    reason: str = ""