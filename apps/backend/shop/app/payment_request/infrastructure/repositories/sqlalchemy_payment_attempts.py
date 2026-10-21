from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.payment_request.domain.entities.payment_attempt import PaymentAttempt
from app.payment_request.domain.interfaces.payment_attempts import PaymentAttempts
from app.payment_request.infrastructure.models.payment_attempt_model import PaymentAttemptModel


class SqlAlchemyPaymentAttempts(PaymentAttempts):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_order(self, order_id: str) -> list[PaymentAttempt]:
        rows = self._session.scalars(
            select(PaymentAttemptModel)
            .where(PaymentAttemptModel.order_id == order_id)
            .order_by(PaymentAttemptModel.number)
        )
        return [
            PaymentAttempt(r.id, r.order_id, r.number, r.reference, r.intent_id, r.status)
            for r in rows
        ]

    def add(self, attempt: PaymentAttempt) -> None:
        self._session.add(
            PaymentAttemptModel(
                id=attempt.id,
                order_id=attempt.order_id,
                number=attempt.number,
                reference=attempt.reference,
                intent_id=attempt.intent_id,
                status=attempt.status,
                created_at=datetime.now(UTC),
            )
        )

    def set_status(self, attempt_id: str, status: str) -> None:
        self._session.execute(
            update(PaymentAttemptModel)
            .where(PaymentAttemptModel.id == attempt_id)
            .values(status=status)
        )
