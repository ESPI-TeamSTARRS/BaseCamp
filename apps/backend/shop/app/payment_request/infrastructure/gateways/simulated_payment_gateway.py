import uuid
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.pay.domain.entities.payment_intent_ref import PaymentIntentRef
from app.pay.domain.exceptions.payment_rejected_error import PaymentRejectedError
from app.pay.domain.interfaces.payment_gateway import PaymentGateway
from app.payment_request.domain.entities.payment_attempt import (
    FAILED,
    REQUIRES_CONFIRMATION,
    SUCCEEDED,
)
from app.payment_request.domain.enums.payment_method import PaymentMethod
from app.payment_request.infrastructure.models.simulated_intent_model import SimulatedIntentModel

_RESULT_BY_METHOD = {PaymentMethod.SUCCESS.value: SUCCEEDED, PaymentMethod.DECLINED.value: FAILED}


class SimulatedPaymentGateway(PaymentGateway):
    """Fournisseur simulé sans réseau : aucune clé, aucune donnée bancaire, état en base."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_intent(
        self, order_reference: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> PaymentIntentRef:
        with Session(self._engine) as session:
            existing = self._by_key(session, idempotency_key)
            if existing is not None:
                return self._replay(existing, order_reference, amount_cents)
            row = SimulatedIntentModel(
                id=str(uuid.uuid4()),
                order_reference=order_reference,
                idempotency_key=idempotency_key,
                amount_cents=amount_cents,
                currency=currency,
                status=REQUIRES_CONFIRMATION,
                created_at=datetime.now(UTC),
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                winner = self._by_key(session, idempotency_key)
                if winner is None:
                    raise PaymentRejectedError(conflict=True) from None  # référence déjà utilisée
                return self._replay(winner, order_reference, amount_cents)
            return self._to_ref(row)

    def get_intent(self, intent_id: str) -> PaymentIntentRef:
        with Session(self._engine) as session:
            return self._to_ref(self._get(session, intent_id, lock=False))

    def confirm_intent(
        self, intent_id: str, payment_method: str, idempotency_key: str
    ) -> PaymentIntentRef:
        result = _RESULT_BY_METHOD.get(payment_method)
        if result is None:
            raise PaymentRejectedError(conflict=False)
        with Session(self._engine) as session:
            row = self._get(session, intent_id, lock=True)
            if row.status == REQUIRES_CONFIRMATION:
                row.status = result
                session.commit()
            return self._to_ref(row)

    @staticmethod
    def _by_key(session: Session, idempotency_key: str) -> SimulatedIntentModel | None:
        return session.scalars(
            select(SimulatedIntentModel).where(
                SimulatedIntentModel.idempotency_key == idempotency_key
            )
        ).one_or_none()

    @staticmethod
    def _get(session: Session, intent_id: str, lock: bool) -> SimulatedIntentModel:
        statement = select(SimulatedIntentModel).where(SimulatedIntentModel.id == intent_id)
        row = session.scalars(statement.with_for_update() if lock else statement).one_or_none()
        if row is None:
            raise PaymentRejectedError(conflict=False)
        return row

    def _replay(
        self, row: SimulatedIntentModel, order_reference: str, amount_cents: int
    ) -> PaymentIntentRef:
        if row.order_reference != order_reference or row.amount_cents != amount_cents:
            raise PaymentRejectedError(conflict=False)  # même clé, autre demande
        return self._to_ref(row)

    @staticmethod
    def _to_ref(row: SimulatedIntentModel) -> PaymentIntentRef:
        return PaymentIntentRef(row.id, row.status, row.amount_cents, row.currency)
