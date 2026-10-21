"""Concurrence réelle sur Postgres : une seule modification par version, stock jamais négatif (ignoré sans Postgres)."""

import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from sqlalchemy import Engine, create_engine, text

from app.catalog.__tests__.product_factory import make_product
from app.catalog.domain.entities.product import Product
from app.catalog.infrastructure.models.base import CatalogBase
from app.catalog.infrastructure.repositories.sqlalchemy_admin_product_repository import (
    SqlAlchemyAdminProductRepository,
)

POSTGRES_URL = os.environ.get("APP_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="definir APP_TEST_POSTGRES_URL")

CONTENDERS = 6


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Schéma jetable propre au test : une base existante n'est jamais modifiée."""
    assert POSTGRES_URL is not None
    schema = f"test_admin_{uuid.uuid4().hex[:12]}"
    admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        POSTGRES_URL,
        pool_size=CONTENDERS + 2,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    CatalogBase.metadata.create_all(engine)
    yield engine
    engine.dispose()
    with admin.connect() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


class TestOptimisticConcurrency:
    def test_parallel_edits_from_the_same_version_let_exactly_one_through(
        self, engine: Engine
    ) -> None:
        repository = SqlAlchemyAdminProductRepository(engine)
        product = make_product("tente", stock=50)
        repository.add(product)

        def edit(stock: int) -> Product | None:
            return repository.update(replace(product, stock=stock), expected_version=1)

        with ThreadPoolExecutor(max_workers=CONTENDERS) as pool:
            results = list(pool.map(edit, range(1, CONTENDERS + 1)))

        winners = [r for r in results if r is not None]
        assert len(winners) == 1
        stored = repository.get(product.id)
        assert stored is not None
        assert (stored.version, stored.stock) == (2, winners[0].stock)

    def test_parallel_image_additions_never_exceed_the_maximum(self, engine: Engine) -> None:
        repository = SqlAlchemyAdminProductRepository(engine)
        product = replace(make_product("tente"), image_keys=())
        repository.add(product)

        def add(index: int) -> bool:
            try:
                return repository.append_image(product.id, f"{index}.jpg", max_images=3) is not None
            except Exception:  # TooManyImagesError attendue
                return False

        with ThreadPoolExecutor(max_workers=CONTENDERS) as pool:
            accepted = list(pool.map(add, range(CONTENDERS)))

        stored = repository.get(product.id)
        assert accepted.count(True) == 3
        assert stored is not None and len(stored.image_keys) == 3 and stored.version == 4
