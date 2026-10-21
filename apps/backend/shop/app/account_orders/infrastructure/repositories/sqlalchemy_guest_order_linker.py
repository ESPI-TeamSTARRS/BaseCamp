from sqlalchemy import Engine, func, update
from sqlalchemy.orm import Session

from app.account_orders.domain.interfaces.guest_order_linker import GuestOrderLinker
from app.order.infrastructure.models.order_model import OrderModel


class SqlAlchemyGuestOrderLinker(GuestOrderLinker):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def link(self, user_id: str, email: str) -> int:
        """Un seul UPDATE conditionnel : une commande deja rattachee n'est jamais reprise."""
        normalized = email.strip().casefold()
        with Session(self._engine) as session:
            result = session.execute(
                update(OrderModel)
                .where(OrderModel.user_id.is_(None), func.lower(OrderModel.email) == normalized)
                .values(user_id=user_id)
            )
            session.commit()
            return int(result.rowcount)  # type: ignore[attr-defined]
