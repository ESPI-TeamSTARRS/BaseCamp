from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.intent.domain.value_objects.amount import Amount


@dataclass(frozen=True)
class Refund:
    """Un remboursement émis, avec la clé d'idempotence qui l'a produit (propre à l'appelant).

    `amount_refunded` est le cumul rendu sur l'intention juste après ce remboursement : il fige la
    réponse, qui reste identique à chaque rejeu même si d'autres remboursements suivent.
    """

    id: UUID
    intent_id: UUID
    amount: Amount
    amount_refunded: int
    caller: str
    key: str
    request_hash: str
    created_at: datetime

    @classmethod
    def issue(
        cls,
        intent_id: UUID,
        amount: Amount,
        amount_refunded: int,
        caller: str,
        key: str,
        request_hash: str,
        now: datetime,
    ) -> "Refund":
        return cls(uuid4(), intent_id, amount, amount_refunded, caller, key, request_hash, now)
