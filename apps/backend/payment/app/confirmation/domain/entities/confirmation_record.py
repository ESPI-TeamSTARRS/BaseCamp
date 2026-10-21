from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ConfirmationRecord:
    """Trace d'une clé d'idempotence de confirmation, propre à l'appelant."""

    caller: str
    key: str
    request_hash: str
    intent_id: UUID
