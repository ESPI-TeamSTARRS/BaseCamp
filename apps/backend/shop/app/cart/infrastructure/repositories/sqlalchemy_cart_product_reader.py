from collections.abc import Sequence

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.cart.domain.entities.cart_product import CartProduct
from app.cart.domain.interfaces.cart_product_reader import CartProductReader
from app.cart.infrastructure.models.cart_product_model import CartProductModel


class SqlAlchemyCartProductReader(CartProductReader):
    """Lecteur sans etat : prix et stock sont relus en base a chaque devis."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def find_by_ids(self, product_ids: Sequence[str]) -> list[CartProduct]:
        statement = select(CartProductModel).where(CartProductModel.id.in_(list(product_ids)))
        with Session(self._engine) as session:
            return [
                CartProduct(id=row.id, name=row.name, price_cents=row.price_cents, stock=row.stock)
                for row in session.scalars(statement)
            ]
