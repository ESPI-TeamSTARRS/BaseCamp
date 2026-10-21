from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.order.domain.enums.order_status import OrderStatus
from app.order.infrastructure.models.order_model import OrderModel
from app.payment_request.domain.entities.payable_order import PayableOrder
from app.payment_request.domain.interfaces.payable_orders import PayableOrders


class SqlAlchemyPayableOrders(PayableOrders):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_for_update(self, order_id: str) -> PayableOrder | None:
        row = self._session.scalars(
            select(OrderModel).where(OrderModel.id == order_id).with_for_update()
        ).one_or_none()
        if row is None:
            return None
        return PayableOrder(row.id, row.number, OrderStatus(row.status), row.total_cents)

    def mark_paid(self, order_id: str) -> None:
        self._session.execute(
            update(OrderModel)
            .where(OrderModel.id == order_id)
            .values(status=OrderStatus.PAID.value)
        )
