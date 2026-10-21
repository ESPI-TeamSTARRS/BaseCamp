import hashlib
import json
from uuid import UUID

from app.confirmation.domain.enums.payment_method import PaymentMethod


class ConfirmationFingerprint:
    """Empreinte d'une confirmation : détecte la réutilisation d'une clé pour une autre demande."""

    @staticmethod
    def of(intent_id: UUID, payment_method: PaymentMethod) -> str:
        canonical = json.dumps([str(intent_id), payment_method.value])
        return hashlib.sha256(canonical.encode()).hexdigest()
