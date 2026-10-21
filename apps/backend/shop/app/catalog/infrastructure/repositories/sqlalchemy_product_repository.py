from typing import Any

from sqlalchemy import Engine, Select, func, select
from sqlalchemy.orm import Session

from app.catalog.domain.entities.product import Product
from app.catalog.domain.enums.product_category import ProductCategory
from app.catalog.domain.interfaces.product_lookup import ProductLookup
from app.catalog.domain.interfaces.product_repository import ProductRepository
from app.catalog.infrastructure.mappers.product_mapper import ProductMapper
from app.catalog.infrastructure.models.product_model import ProductModel


class SqlAlchemyProductRepository(ProductRepository, ProductLookup):
    """Depot sans etat : une session courte par appel (aucune donnee gardee en memoire)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_products(
        self, category: ProductCategory | None, limit: int, offset: int
    ) -> list[Product]:
        statement = (
            self._filtered(select(ProductModel), category)
            .order_by(ProductModel.name, ProductModel.id)
            .limit(limit)
            .offset(offset)
        )
        with Session(self._engine) as session:
            return [ProductMapper.to_entity(row) for row in session.scalars(statement)]

    def count(self, category: ProductCategory | None) -> int:
        statement = self._filtered(select(func.count()).select_from(ProductModel), category)
        with Session(self._engine) as session:
            return session.scalar(statement) or 0

    def get_by_slug(self, slug: str) -> Product | None:
        statement = select(ProductModel).where(
            ProductModel.slug == slug, ProductModel.archived_at.is_(None)
        )
        with Session(self._engine) as session:
            row = session.scalars(statement).first()
            return ProductMapper.to_entity(row) if row else None

    @staticmethod
    def _filtered(statement: Select[Any], category: ProductCategory | None) -> Select[Any]:
        visible = statement.where(ProductModel.archived_at.is_(None))  # archivé = disparu
        if category is None:
            return visible
        return visible.where(ProductModel.category == category.value)
