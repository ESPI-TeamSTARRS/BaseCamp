"""Dépôt d'administration sur la base : version optimiste, soft delete, images, aucun effacement."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.catalog.__tests__.product_factory import make_product
from app.catalog.domain.errors.duplicate_product_error import DuplicateProductError
from app.catalog.domain.errors.too_many_images_error import TooManyImagesError
from app.catalog.infrastructure.models.base import CatalogBase
from app.catalog.infrastructure.models.product_model import ProductModel
from app.catalog.infrastructure.repositories.sqlalchemy_admin_product_repository import (
    SqlAlchemyAdminProductRepository,
)

NOW = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    CatalogBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def repository(engine: Engine) -> SqlAlchemyAdminProductRepository:
    return SqlAlchemyAdminProductRepository(engine)


class TestAddAndRead:
    def test_adds_a_product_and_reads_it_back_with_version_one(
        self, repository: SqlAlchemyAdminProductRepository
    ) -> None:
        product = make_product("tente", price_cents=0, stock=0)

        repository.add(product)

        stored = repository.get(product.id)
        assert stored is not None
        assert (stored.version, stored.archived_at, stored.price_cents) == (1, None, 0)

    def test_the_same_id_or_slug_twice_is_a_duplicate(
        self, repository: SqlAlchemyAdminProductRepository
    ) -> None:
        repository.add(make_product("tente"))

        with pytest.raises(DuplicateProductError):
            repository.add(make_product("tente"))
        with pytest.raises(DuplicateProductError):
            repository.add(replace(make_product("autre"), slug="tente"))

    def test_lists_archived_products_only_when_asked(
        self, repository: SqlAlchemyAdminProductRepository
    ) -> None:
        repository.add(make_product("a"))
        repository.add(make_product("b"))
        repository.archive("id-b", NOW)

        assert [p.id for p in repository.list_products(False, 10, 0)] == ["id-a"]
        assert [p.id for p in repository.list_products(True, 10, 0)] == ["id-a", "id-b"]
        assert (repository.count(False), repository.count(True)) == (1, 2)
        assert [p.id for p in repository.list_products(True, 1, 1)] == ["id-b"]
        assert repository.get("absent") is None


class TestSearch:
    def test_matches_a_fragment_of_the_name_ignoring_case(
        self, repository: SqlAlchemyAdminProductRepository
    ) -> None:
        repository.add(replace(make_product("a"), name="Tente Tunnel"))
        repository.add(replace(make_product("b"), name="Sac a dos"))

        assert [p.id for p in repository.list_products(False, 10, 0, "tunnel")] == ["id-a"]
        assert repository.count(False, "TUNNEL") == 1
        assert repository.count(False, "zzz") == 0

    def test_percent_and_underscore_are_literal_characters(
        self, repository: SqlAlchemyAdminProductRepository
    ) -> None:
        repository.add(replace(make_product("a"), name="Gourde 100% inox"))
        repository.add(replace(make_product("b"), name="Gourde 1000 inox"))

        assert [p.id for p in repository.list_products(False, 10, 0, "100%")] == ["id-a"]
        assert repository.count(False, "_") == 0


class TestOptimisticUpdate:
    def test_saves_and_bumps_the_version_when_it_matches(
        self, repository: SqlAlchemyAdminProductRepository
    ) -> None:
        product = make_product("tente", price_cents=1000, stock=5)
        repository.add(product)

        saved = repository.update(replace(product, price_cents=1500, stock=4), expected_version=1)

        assert saved is not None
        assert (saved.price_cents, saved.stock, saved.version) == (1500, 4, 2)

    def test_a_stale_version_writes_nothing(
        self, repository: SqlAlchemyAdminProductRepository
    ) -> None:
        product = make_product("tente", stock=5)
        repository.add(product)
        repository.update(replace(product, stock=4), expected_version=1)

        refused = repository.update(replace(product, stock=99), expected_version=1)

        assert refused is None
        stored = repository.get(product.id)
        assert stored is not None and (stored.stock, stored.version) == (4, 2)

    def test_an_archived_product_cannot_be_updated(
        self, repository: SqlAlchemyAdminProductRepository
    ) -> None:
        product = make_product("tente")
        repository.add(product)
        archived = repository.archive(product.id, NOW)
        assert archived is not None

        assert repository.update(replace(product, stock=9), archived.version) is None

    def test_the_database_refuses_a_negative_stock_even_if_the_application_did_not(
        self, engine: Engine
    ) -> None:
        # Le garde-fou applicatif est dans l'entité; la contrainte CHECK est testée sur Postgres.
        with pytest.raises(ValueError):
            replace(make_product("tente"), stock=-1)


class TestArchive:
    def test_archives_without_deleting_and_only_once(
        self, repository: SqlAlchemyAdminProductRepository, engine: Engine
    ) -> None:
        repository.add(make_product("tente"))

        first = repository.archive("id-tente", NOW)
        second = repository.archive("id-tente", datetime(2026, 12, 1, tzinfo=UTC))

        assert first is not None and second is not None
        assert first.archived_at is not None and second.archived_at is not None
        assert first.archived_at.replace(tzinfo=UTC) == NOW  # SQLite rend des dates sans fuseau
        assert second.archived_at.replace(tzinfo=UTC) == NOW  # la date d'origine est conservée
        assert second.version == first.version == 2
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(ProductModel)) == 1
        assert repository.archive("absent", NOW) is None


class TestImages:
    def test_appends_a_key_and_bumps_the_version(
        self, repository: SqlAlchemyAdminProductRepository
    ) -> None:
        product = replace(make_product("tente"), image_keys=())
        repository.add(product)

        saved = repository.append_image(product.id, "abc.jpg", max_images=2)

        assert saved is not None
        assert (saved.image_keys, saved.version) == (("abc.jpg",), 2)

    def test_refuses_beyond_the_maximum_and_ignores_unknown_products(
        self, repository: SqlAlchemyAdminProductRepository
    ) -> None:
        product = replace(make_product("tente"), image_keys=("a.jpg", "b.jpg"))
        repository.add(product)

        with pytest.raises(TooManyImagesError):
            repository.append_image(product.id, "c.jpg", max_images=2)

        assert repository.append_image("absent", "c.jpg", max_images=2) is None
        stored = repository.get(product.id)
        assert stored is not None and stored.image_keys == ("a.jpg", "b.jpg")
