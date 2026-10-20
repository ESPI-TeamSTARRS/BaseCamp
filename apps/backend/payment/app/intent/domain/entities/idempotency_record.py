from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class IdempotencyRecord:
    """Trace d'une clé d'idempotence, propre à l'appelant, liée à l'intention qu'elle a créée."""

    caller: str
    key: str
    request_hash: str
    intent_id: UUID
