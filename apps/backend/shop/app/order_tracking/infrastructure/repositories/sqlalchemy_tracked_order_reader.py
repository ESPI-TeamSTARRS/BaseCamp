from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.order.infrastructure.models.order_line_model import OrderLineModel
from app.order.infrastructure.models.order_model import OrderModel
from app.order_tracking.domain.entities.tracked_line import TrackedLine
from app.order_tracking.domain.entities.tracked_order import TrackedOrder
from app.order_tracking.domain.interfaces.tracked_order_reader import TrackedOrderReader

_NO_ORDER = "-"


class SqlAlchemyTrackedOrderReader(TrackedOrderReader):
    """Lecteur sans état : le numéro est un paramètre lié, jamais concaténé."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def find_by_number(self, number: str) -> TrackedOrder | None:
        with Session(self._engine) as session:
            row = session.scalars(
                select(OrderModel).where(OrderModel.number == number)
            ).one_or_none()
            # Les lignes sont toujours lues, même sans commande : deux requêtes dans les deux cas.
            lines = session.scalars(
                select(OrderLineModel)
                .where(OrderLineModel.order_id == (row.id if row is not None else _NO_ORDER))
                .order_by(OrderLineModel.position)
            ).all()
            if row is None:
                return None
            return TrackedOrder(
                number=row.number,
                email=row.email,
                status=row.status,
                lines=tuple(
                    TrackedLine(line.product_name, line.unit_price_cents, line.quantity)
                    for line in lines
                ),
                subtotal_cents=row.subtotal_cents,
                shipping_cents=row.shipping_cents,
                total_cents=row.total_cents,
                created_at=row.created_at,
            )
