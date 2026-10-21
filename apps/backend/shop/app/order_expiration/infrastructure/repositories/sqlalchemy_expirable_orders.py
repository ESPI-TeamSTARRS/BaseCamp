from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.order.domain.enums.order_status import OrderStatus
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.models.order_product_model import OrderProductModel
from app.order.infrastructure.models.stock_reservation_model import StockReservationModel
from app.order_expiration.domain.entities.expirable_order import ExpirableOrder
from app.order_expiration.domain.entities.released_line import ReleasedLine
from app.order_expiration.domain.interfaces.expirable_orders import ExpirableOrders


def _as_utc(value: datetime) -> datetime:
    """Postgres renvoie des dates avec fuseau; SQLite (tests) les rend sans : on les lit en UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


RESERVED = "reserved"
RELEASED = "released"


class SqlAlchemyExpirableOrders(ExpirableOrders):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_expirable(self, created_before: datetime, limit: int) -> list[ExpirableOrder]:
        rows = self._session.scalars(
            select(OrderModel)
            .where(
                OrderModel.status == OrderStatus.PENDING_PAYMENT.value,
                OrderModel.created_at < created_before,
            )
            .order_by(OrderModel.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)  # un paiement en cours garde sa commande
        )
        return [ExpirableOrder(row.id, row.number, _as_utc(row.created_at)) for row in rows]

    def expire(self, order_id: str) -> None:
        self._session.execute(
            update(OrderModel)
            .where(OrderModel.id == order_id)
            .values(status=OrderStatus.EXPIRED.value)
        )

    def release_reservations(self, order_id: str) -> list[ReleasedLine]:
        reservations = self._session.scalars(
            select(StockReservationModel)
            .where(
                StockReservationModel.order_id == order_id,
                StockReservationModel.status == RESERVED,
            )
            .order_by(StockReservationModel.product_id)  # même ordre partout : pas d'interblocage
        ).all()
        for reservation in reservations:
            self._session.execute(
                update(OrderProductModel)
                .where(OrderProductModel.id == reservation.product_id)
                .values(stock=OrderProductModel.stock + reservation.quantity)
            )
            reservation.status = RELEASED
        return [ReleasedLine(r.product_id, r.quantity) for r in reservations]
