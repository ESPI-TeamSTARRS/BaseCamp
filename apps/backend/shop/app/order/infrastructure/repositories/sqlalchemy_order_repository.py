from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.order.domain.entities.order import Order
from app.order.domain.entities.order_line import OrderLine
from app.order.domain.enums.order_status import OrderStatus
from app.order.domain.enums.shipping_country import ShippingCountry
from app.order.domain.errors.duplicate_idempotency_key_error import DuplicateIdempotencyKeyError
from app.order.domain.interfaces.order_repository import OrderRepository
from app.order.domain.value_objects.shipping_address import ShippingAddress
from app.order.infrastructure.models.order_line_model import OrderLineModel
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.repositories.idempotency_violation import is_idempotency_violation


class SqlAlchemyOrderRepository(OrderRepository):
    """Depot lie a la session de l'unite de travail : rien n'est valide ici."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        row = self._session.scalars(
            select(OrderModel).where(OrderModel.idempotency_key == idempotency_key)
        ).one_or_none()
        if row is None:
            return None
        lines = self._session.scalars(
            select(OrderLineModel)
            .where(OrderLineModel.order_id == row.id)
            .order_by(OrderLineModel.position)
        ).all()
        return self._to_entity(row, lines)

    def add(self, order: Order) -> None:
        self._session.add(self._to_model(order))
        self._flush_order()
        self._session.add_all(
            OrderLineModel(
                order_id=order.id,
                position=position,
                product_id=line.product_id,
                product_name=line.product_name,
                unit_price_cents=line.unit_price_cents,
                quantity=line.quantity,
            )
            for position, line in enumerate(order.lines)
        )

    def _flush_order(self) -> None:
        # Sans relationship(), SQLAlchemy ne deduit pas l'ordre d'insertion des cles etrangeres.
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            if is_idempotency_violation(error):
                raise DuplicateIdempotencyKeyError from None
            raise

    @staticmethod
    def _to_model(order: Order) -> OrderModel:
        address = order.address
        return OrderModel(
            id=order.id,
            number=order.number,
            status=order.status.value,
            email=order.email,
            ship_full_name=address.full_name,
            ship_line1=address.line1,
            ship_line2=address.line2,
            ship_postal_code=address.postal_code,
            ship_city=address.city,
            ship_country=address.country.value,
            subtotal_cents=order.subtotal_cents,
            shipping_cents=order.shipping_cents,
            total_cents=order.total_cents,
            idempotency_key=order.idempotency_key,
            request_fingerprint=order.request_fingerprint,
            created_at=order.created_at,
        )

    @staticmethod
    def _to_entity(row: OrderModel, lines: Sequence[OrderLineModel]) -> Order:
        return Order(
            id=row.id,
            number=row.number,
            status=OrderStatus(row.status),
            email=row.email,
            address=ShippingAddress(
                full_name=row.ship_full_name,
                line1=row.ship_line1,
                line2=row.ship_line2,
                postal_code=row.ship_postal_code,
                city=row.ship_city,
                country=ShippingCountry(row.ship_country),
            ),
            lines=tuple(
                OrderLine(line.product_id, line.product_name, line.unit_price_cents, line.quantity)
                for line in lines
            ),
            idempotency_key=row.idempotency_key,
            request_fingerprint=row.request_fingerprint,
            created_at=row.created_at,
        )
