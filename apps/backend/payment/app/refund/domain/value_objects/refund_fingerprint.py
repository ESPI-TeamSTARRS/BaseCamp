import hashlib
import json
from uuid import UUID

from app.intent.domain.value_objects.amount import Amount


class RefundFingerprint:
    """Empreinte d'un remboursement : détecte la réutilisation d'une clé pour une autre demande."""

    @staticmethod
    def of(intent_id: UUID, amount: Amount) -> str:
        canonical = json.dumps([str(intent_id), amount.cents])
        return hashlib.sha256(canonical.encode()).hexdigest()
