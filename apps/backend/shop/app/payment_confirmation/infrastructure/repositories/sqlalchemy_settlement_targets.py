from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.order.domain.enums.order_status import OrderStatus
from app.order.infrastructure.models.order_line_model import OrderLineModel
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.models.stock_reservation_model import StockReservationModel
from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.entities.mail_line import MailLine
from app.payment_confirmation.domain.entities.settlement_target import SettlementTarget
from app.payment_confirmation.domain.interfaces.settlement_targets import SettlementTargets
from app.payment_request.infrastructure.models.order_refund_model import OrderRefundModel
from app.payment_request.infrastructure.models.payment_attempt_model import PaymentAttemptModel

RESERVED = "reserved"
COMMITTED = "committed"


class SqlAlchemySettlementTargets(SettlementTargets):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_for_update(self, reference: str) -> SettlementTarget | None:
        attempt = self._session.scalars(
            select(PaymentAttemptModel).where(PaymentAttemptModel.reference == reference)
        ).one_or_none()
        if attempt is None:
            return None
        order = self._session.scalars(
            select(OrderModel).where(OrderModel.id == attempt.order_id).with_for_update()
        ).one()
        # La tentative est relue sous le verrou de la commande : son statut est celui du commit précédent.
        self._session.refresh(attempt)
        refunded = self._session.scalar(
            select(OrderRefundModel.refunded_cents).where(OrderRefundModel.order_id == order.id)
        )
        return SettlementTarget(
            order_id=order.id,
            order_number=order.number,
            order_status=OrderStatus(order.status),
            total_cents=order.total_cents,
            attempt_id=attempt.id,
            attempt_status=attempt.status,
            refunded_cents=refunded or 0,
        )

    def mark_paid(self, order_id: str) -> None:
        self._session.execute(
            update(OrderModel)
            .where(OrderModel.id == order_id)
            .values(status=OrderStatus.PAID.value)
        )

    def record_refund(self, order_id: str, refunded_cents: int) -> None:
        # La commande est verrouillée (find_for_update) : lire puis écrire est sans concurrence.
        now = datetime.now(UTC)
        row = self._session.get(OrderRefundModel, order_id)
        if row is None:
            self._session.add(
                OrderRefundModel(order_id=order_id, refunded_cents=refunded_cents, updated_at=now)
            )
        else:
            row.refunded_cents = refunded_cents
            row.updated_at = now
        self._session.execute(
            update(OrderModel)
            .where(OrderModel.id == order_id, OrderModel.total_cents <= refunded_cents)
            .values(status=OrderStatus.REFUNDED.value)
        )

    def set_attempt_status(self, attempt_id: str, status: str) -> None:
        self._session.execute(
            update(PaymentAttemptModel)
            .where(PaymentAttemptModel.id == attempt_id)
            .values(status=status)
        )

    def commit_reservations(self, order_id: str) -> int:
        """Le stock a été retiré à la commande : on ne fait que rendre la réservation définitive."""
        result = self._session.execute(
            update(StockReservationModel)
            .where(
                StockReservationModel.order_id == order_id,
                StockReservationModel.status == RESERVED,
            )
            .values(status=COMMITTED)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def mail_for(self, order_id: str) -> ConfirmationMail:
        order = self._session.scalars(select(OrderModel).where(OrderModel.id == order_id)).one()
        lines = self._session.scalars(
            select(OrderLineModel)
            .where(OrderLineModel.order_id == order_id)
            .order_by(OrderLineModel.position)
        ).all()
        return ConfirmationMail(
            to=order.email,
            order_number=order.number,
            total_cents=order.total_cents,
            lines=tuple(
                MailLine(line.product_name, line.quantity, line.unit_price_cents * line.quantity)
                for line in lines
            ),
        )
