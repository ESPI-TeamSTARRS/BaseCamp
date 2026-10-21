from datetime import UTC, datetime

from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog.domain.entities.product import Product
from app.catalog.domain.errors.duplicate_product_error import DuplicateProductError
from app.catalog.domain.errors.too_many_images_error import TooManyImagesError
from app.catalog.domain.interfaces.admin_product_repository import AdminProductRepository
from app.catalog.infrastructure.mappers.product_mapper import ProductMapper
from app.catalog.infrastructure.models.product_model import ProductModel


class SqlAlchemyAdminProductRepository(AdminProductRepository):
    """Dépôt sans état : une transaction courte par appel, jamais de DELETE (archivage seulement)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_products(self, include_archived: bool, limit: int, offset: int) -> list[Product]:
        statement = select(ProductModel)
        if not include_archived:
            statement = statement.where(ProductModel.archived_at.is_(None))
        statement = (
            statement.order_by(ProductModel.name, ProductModel.id).limit(limit).offset(offset)
        )
        with Session(self._engine) as session:
            return [ProductMapper.to_entity(row) for row in session.scalars(statement)]

    def count(self, include_archived: bool) -> int:
        statement = select(func.count()).select_from(ProductModel)
        if not include_archived:
            statement = statement.where(ProductModel.archived_at.is_(None))
        with Session(self._engine) as session:
            return session.scalar(statement) or 0

    def get(self, product_id: str) -> Product | None:
        with Session(self._engine) as session:
            row = session.get(ProductModel, product_id)
            return ProductMapper.to_entity(row) if row else None

    def add(self, product: Product) -> None:
        with Session(self._engine) as session:
            session.add(ProductMapper.to_model(product))
            try:
                session.commit()
            except IntegrityError:
                raise DuplicateProductError from None

    def update(self, product: Product, expected_version: int) -> Product | None:
        values = ProductMapper.to_model(product)
        with Session(self._engine) as session:
            result = session.execute(
                update(ProductModel)
                .where(
                    ProductModel.id == product.id,
                    ProductModel.version == expected_version,
                    ProductModel.archived_at.is_(None),
                )
                .values(
                    name=values.name,
                    category=values.category,
                    price_cents=values.price_cents,
                    compare_at_price_cents=values.compare_at_price_cents,
                    short_description=values.short_description,
                    description=values.description,
                    specs=values.specs,
                    stock=values.stock,
                    version=ProductModel.version + 1,
                )
            )
            if result.rowcount != 1:  # type: ignore[attr-defined]
                return None
            session.commit()
            row = session.get(ProductModel, product.id)
            return ProductMapper.to_entity(row) if row else None

    def archive(self, product_id: str, at: datetime) -> Product | None:
        with Session(self._engine) as session:
            row = session.scalars(
                select(ProductModel).where(ProductModel.id == product_id).with_for_update()
            ).one_or_none()
            if row is None:
                return None
            if row.archived_at is None:
                row.archived_at = at.astimezone(UTC)
                row.version += 1
                session.commit()
            return ProductMapper.to_entity(row)

    def append_image(self, product_id: str, key: str, max_images: int) -> Product | None:
        with Session(self._engine) as session:
            row = session.scalars(
                select(ProductModel).where(ProductModel.id == product_id).with_for_update()
            ).one_or_none()
            if row is None:
                return None
            if len(row.images) >= max_images:
                raise TooManyImagesError
            row.images = [*row.images, key]  # nouvelle liste : le changement est détecté
            row.version += 1
            session.commit()
            return ProductMapper.to_entity(row)
