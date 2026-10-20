import hashlib
import json

from app.intent.domain.enums.currency import Currency


class RequestFingerprint:
    """Empreinte d'une demande de création : détecte la réutilisation d'une clé avec un autre corps."""

    @staticmethod
    def of(order_reference: str, amount_cents: int, currency: Currency) -> str:
        canonical = json.dumps([order_reference, amount_cents, currency.value])
        return hashlib.sha256(canonical.encode()).hexdigest()
