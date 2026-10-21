from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.order.domain.entities.stock_item import StockItem
from app.order.domain.interfaces.stock_ledger import StockLedger
from app.order.infrastructure.models.order_product_model import OrderProductModel
from app.order.infrastructure.models.stock_reservation_model import StockReservationModel

RESERVED = "reserved"


class SqlAlchemyStockLedger(StockLedger):
    """Verrou de ligne (FOR UPDATE) puis decrement : le stock ne passe jamais sous zero."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def lock_items(self, product_ids: Sequence[str]) -> list[StockItem]:
        statement = (
            select(OrderProductModel)
            .where(OrderProductModel.id.in_(list(product_ids)))
            .order_by(OrderProductModel.id)  # meme ordre partout : pas d'interblocage
            .with_for_update()
        )
        return [
            StockItem(row.id, row.name, row.price_cents, row.stock)
            for row in self._session.scalars(statement)
        ]

    def reserve(self, order_id: str, product_id: str, quantity: int) -> None:
        self._session.execute(
            update(OrderProductModel)
            .where(OrderProductModel.id == product_id)
            .values(stock=OrderProductModel.stock - quantity)
        )
        self._session.add(
            StockReservationModel(
                order_id=order_id, product_id=product_id, quantity=quantity, status=RESERVED
            )
        )
