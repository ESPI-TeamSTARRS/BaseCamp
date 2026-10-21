from collections.abc import Sequence

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.account_orders.domain.entities.account_order import AccountOrder
from app.account_orders.domain.entities.account_order_line import AccountOrderLine
from app.account_orders.domain.entities.account_order_page import AccountOrderPage
from app.account_orders.domain.interfaces.account_order_reader import AccountOrderReader
from app.order.infrastructure.models.order_line_model import OrderLineModel
from app.order.infrastructure.models.order_model import OrderModel


class SqlAlchemyAccountOrderReader(AccountOrderReader):
    """Lecteur sans etat : le compte est TOUJOURS une condition de la requete (parametre lie)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_for_user(self, user_id: str, limit: int, offset: int) -> AccountOrderPage:
        with Session(self._engine) as session:
            total = session.scalar(
                select(func.count()).select_from(OrderModel).where(OrderModel.user_id == user_id)
            )
            rows = session.scalars(
                select(OrderModel)
                .where(OrderModel.user_id == user_id)
                .order_by(OrderModel.created_at.desc(), OrderModel.id)
                .limit(limit)
                .offset(offset)
            ).all()
            lines = self._lines(session, [row.id for row in rows])
            items = tuple(self._order(row, lines.get(row.id, ())) for row in rows)
            return AccountOrderPage(items, int(total or 0), limit, offset)

    def find_for_user(self, user_id: str, order_id: str) -> AccountOrder | None:
        with Session(self._engine) as session:
            row = session.scalars(
                select(OrderModel).where(OrderModel.id == order_id, OrderModel.user_id == user_id)
            ).one_or_none()
            if row is None:
                return None
            return self._order(row, self._lines(session, [row.id]).get(row.id, ()))

    @staticmethod
    def _lines(
        session: Session, order_ids: Sequence[str]
    ) -> dict[str, tuple[AccountOrderLine, ...]]:
        if not order_ids:
            return {}
        grouped: dict[str, list[AccountOrderLine]] = {}
        for line in session.scalars(
            select(OrderLineModel)
            .where(OrderLineModel.order_id.in_(order_ids))
            .order_by(OrderLineModel.order_id, OrderLineModel.position)
        ):
            grouped.setdefault(line.order_id, []).append(
                AccountOrderLine(line.product_name, line.unit_price_cents, line.quantity)
            )
        return {order_id: tuple(lines) for order_id, lines in grouped.items()}

    @staticmethod
    def _order(row: OrderModel, lines: tuple[AccountOrderLine, ...]) -> AccountOrder:
        return AccountOrder(
            id=row.id,
            number=row.number,
            status=row.status,
            lines=lines,
            subtotal_cents=row.subtotal_cents,
            shipping_cents=row.shipping_cents,
            total_cents=row.total_cents,
            created_at=row.created_at,
        )
