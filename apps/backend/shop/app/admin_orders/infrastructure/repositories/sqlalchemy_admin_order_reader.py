from collections.abc import Sequence
from typing import Any

from sqlalchemy import Engine, Select, func, or_, select
from sqlalchemy.orm import Session

from app.admin_orders.domain.entities.admin_order import AdminOrder
from app.admin_orders.domain.entities.admin_order_line import AdminOrderLine
from app.admin_orders.domain.entities.admin_order_page import AdminOrderPage
from app.admin_orders.domain.entities.admin_order_summary import AdminOrderSummary
from app.admin_orders.domain.entities.admin_shipping_address import AdminShippingAddress
from app.admin_orders.domain.interfaces.admin_order_reader import AdminOrderReader
from app.order.infrastructure.models.order_line_model import OrderLineModel
from app.order.infrastructure.models.order_model import OrderModel


class SqlAlchemyAdminOrderReader(AdminOrderReader):
    """Lecteur sans etat et sans ecriture : filtre et recherche sont des parametres lies."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_orders(
        self, status: str | None, search: str | None, limit: int, offset: int
    ) -> AdminOrderPage:
        with Session(self._engine) as session:
            total = session.scalar(
                self._filtered(select(func.count()).select_from(OrderModel), status, search)
            )
            rows = session.scalars(
                self._filtered(select(OrderModel), status, search)
                .order_by(OrderModel.created_at.desc(), OrderModel.id)
                .limit(limit)
                .offset(offset)
            ).all()
            counts = self._item_counts(session, [row.id for row in rows])
            items = tuple(
                AdminOrderSummary(
                    id=row.id,
                    number=row.number,
                    status=row.status,
                    email=row.email,
                    total_cents=row.total_cents,
                    item_count=counts.get(row.id, 0),
                    created_at=row.created_at,
                )
                for row in rows
            )
            return AdminOrderPage(items, int(total or 0), limit, offset)

    def find(self, order_id: str) -> AdminOrder | None:
        with Session(self._engine) as session:
            row = session.get(OrderModel, order_id)
            if row is None:
                return None
            lines = tuple(
                AdminOrderLine(line.product_name, line.unit_price_cents, line.quantity)
                for line in session.scalars(
                    select(OrderLineModel)
                    .where(OrderLineModel.order_id == row.id)
                    .order_by(OrderLineModel.position)
                )
            )
            return AdminOrder(
                id=row.id,
                number=row.number,
                status=row.status,
                email=row.email,
                shipping_address=AdminShippingAddress(
                    full_name=row.ship_full_name,
                    line1=row.ship_line1,
                    line2=row.ship_line2,
                    postal_code=row.ship_postal_code,
                    city=row.ship_city,
                    country=row.ship_country,
                ),
                lines=lines,
                subtotal_cents=row.subtotal_cents,
                shipping_cents=row.shipping_cents,
                total_cents=row.total_cents,
                created_at=row.created_at,
            )

    @staticmethod
    def _filtered(statement: Select[Any], status: str | None, search: str | None) -> Select[Any]:
        if status:
            statement = statement.where(OrderModel.status == status)
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            statement = statement.where(
                or_(
                    OrderModel.number.ilike(pattern, escape="\\"),
                    OrderModel.email.ilike(pattern, escape="\\"),
                )
            )
        return statement

    @staticmethod
    def _item_counts(session: Session, order_ids: Sequence[str]) -> dict[str, int]:
        if not order_ids:
            return {}
        rows = session.execute(
            select(OrderLineModel.order_id, func.sum(OrderLineModel.quantity))
            .where(OrderLineModel.order_id.in_(order_ids))
            .group_by(OrderLineModel.order_id)
        ).all()
        return {order_id: int(quantity or 0) for order_id, quantity in rows}
