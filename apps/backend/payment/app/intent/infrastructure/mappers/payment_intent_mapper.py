from datetime import UTC, datetime

from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.value_objects.amount import Amount
from app.intent.infrastructure.models.payment_intent_model import PaymentIntentModel


class PaymentIntentMapper:
    """Conversion entre l'entité du domaine et le modèle SQLAlchemy (partagée entre tranches)."""

    @staticmethod
    def to_utc(value: datetime) -> datetime:
        """Certains moteurs (SQLite) renvoient des dates sans fuseau : tout est en UTC."""
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @classmethod
    def to_entity(cls, model: PaymentIntentModel) -> PaymentIntent:
        return PaymentIntent(
            id=model.id,
            order_reference=model.order_reference,
            amount=Amount(model.amount),
            currency=Currency(model.currency),
            status=IntentStatus(model.status),
            refunded_amount=model.refunded_amount,
            expires_at=cls.to_utc(model.expires_at),
            created_at=cls.to_utc(model.created_at),
        )

    @staticmethod
    def to_model(intent: PaymentIntent) -> PaymentIntentModel:
        return PaymentIntentModel(
            id=intent.id,
            order_reference=intent.order_reference,
            amount=intent.amount.cents,
            currency=intent.currency.value,
            status=intent.status.value,
            refunded_amount=intent.refunded_amount,
            expires_at=intent.expires_at,
            created_at=intent.created_at,
        )
