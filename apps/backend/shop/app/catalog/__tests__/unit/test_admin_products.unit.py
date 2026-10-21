"""Administration du catalogue : création, modification concurrente, archivage, événement métier."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.catalog.__tests__.admin_fakes import OPERATOR_ID, InMemoryAdminProducts
from app.catalog.__tests__.product_factory import make_product
from app.catalog.application.archive_product import ArchiveProductUseCase
from app.catalog.application.create_product import CreateProductUseCase
from app.catalog.application.invalid_product_error import InvalidProductError
from app.catalog.application.list_admin_products import ListAdminProductsUseCase
from app.catalog.application.new_product import NewProduct
from app.catalog.application.product_conflict_error import ProductConflictError
from app.catalog.application.product_not_found_error import ProductNotFoundError
from app.catalog.application.update_product import UpdateProductUseCase
from app.catalog.application.update_product_command import UpdateProductCommand
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger

NOW = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)
OPERATOR = UUID(OPERATOR_ID)


class _Pseudonymizer:
    def pseudonymize(self, value: str) -> str:
        return "pseudo-" + value[:4]


def _new(**overrides: object) -> NewProduct:
    fields: dict[str, object] = {
        "name": "Tente Tunnel 4 Saisons",
        "slug": None,
        "category": "tentes",
        "price_cents": 24900,
        "compare_at_price_cents": None,
        "short_description": "Tente robuste",
        "description": "Une tente pour toutes les saisons.",
        "specs": {"weight_grams": 3200},
        "stock": 8,
    }
    fields.update(overrides)
    return NewProduct(**fields)  # type: ignore[arg-type]


class _Setup:
    def __init__(self, *products: object) -> None:
        self.repository = InMemoryAdminProducts(*products)  # type: ignore[arg-type]
        self.events = InMemoryBusinessEventLogger()
        args = (self.repository, self.events, _Pseudonymizer())
        self.create = CreateProductUseCase(*args)
        self.update = UpdateProductUseCase(*args)
        self.archive = ArchiveProductUseCase(*args, clock=lambda: NOW)


class TestCreateProduct:
    def test_creates_a_product_with_a_slug_derived_from_its_name(self) -> None:
        setup = _Setup()

        product = setup.create.execute(OPERATOR, _new())

        assert (product.id, product.slug) == ("tente-tunnel-4-saisons",) * 2
        assert (product.price_cents, product.stock, product.version) == (24900, 8, 1)
        assert (product.rating_value, product.rating_count, product.image_keys) == (0.0, 0, ())
        assert setup.repository.get(product.id) == product

    def test_a_price_of_zero_and_a_stock_of_zero_are_valid(self) -> None:
        product = _Setup().create.execute(OPERATOR, _new(price_cents=0, stock=0))

        assert (product.price_cents, product.stock) == (0, 0)

    def test_the_same_slug_twice_is_a_conflict(self) -> None:
        setup = _Setup()
        setup.create.execute(OPERATOR, _new())

        with pytest.raises(ProductConflictError) as error:
            setup.create.execute(OPERATOR, _new(name="Autre nom", slug="tente-tunnel-4-saisons"))

        assert error.value.reason == "duplicate_product"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"category": "inconnue"},
            {"name": "   "},
            {"slug": "Pas Un Slug"},
            {"slug": "-tiret"},
            {"price_cents": -1},
            {"stock": -1},
            {"compare_at_price_cents": -5},
            {"specs": {"weight_grams": -3}},
            {"specs": {"inconnu": 1}},
            {"name": "!!!"},
        ],
    )
    def test_invalid_data_is_refused_without_any_write(self, overrides: dict[str, object]) -> None:
        setup = _Setup()

        with pytest.raises(InvalidProductError):
            setup.create.execute(OPERATOR, _new(**overrides))

        assert setup.repository.products == {}
        assert setup.events.events == []


class TestUpdateProduct:
    def _existing(self) -> object:
        return make_product("tente")

    def test_updates_only_the_given_fields_and_bumps_the_version(self) -> None:
        existing = make_product("tente", price_cents=10000, stock=5)
        setup = _Setup(existing)

        updated = setup.update.execute(
            OPERATOR, UpdateProductCommand(existing.id, 1, {"price_cents": 12000})
        )

        assert (updated.price_cents, updated.stock, updated.name) == (12000, 5, existing.name)
        assert updated.version == 2

    def test_a_stale_version_is_a_conflict_and_changes_nothing(self) -> None:
        existing = make_product("tente", price_cents=10000)
        setup = _Setup(existing)
        setup.update.execute(OPERATOR, UpdateProductCommand(existing.id, 1, {"stock": 3}))

        with pytest.raises(ProductConflictError) as error:
            setup.update.execute(OPERATOR, UpdateProductCommand(existing.id, 1, {"stock": 99}))

        assert error.value.reason == "stale_version"
        assert setup.repository.get(existing.id).stock == 3  # type: ignore[union-attr]

    def test_the_stock_can_never_go_below_zero(self) -> None:
        existing = make_product("tente")
        setup = _Setup(existing)

        with pytest.raises(InvalidProductError):
            setup.update.execute(OPERATOR, UpdateProductCommand(existing.id, 1, {"stock": -1}))

        assert setup.repository.get(existing.id).version == 1  # type: ignore[union-attr]

    def test_an_unknown_product_is_not_found_and_an_archived_one_is_a_conflict(self) -> None:
        archived = replace(make_product("vieux"), archived_at=NOW)
        setup = _Setup(archived)

        with pytest.raises(ProductNotFoundError):
            setup.update.execute(OPERATOR, UpdateProductCommand("absent", 1, {"stock": 1}))
        with pytest.raises(ProductConflictError) as error:
            setup.update.execute(OPERATOR, UpdateProductCommand(archived.id, 1, {"stock": 1}))

        assert error.value.reason == "product_archived"

    @pytest.mark.parametrize(
        "changes",
        [{"slug": "autre"}, {"id": "x"}, {"images": []}, {"version": 9}, {"category": "nope"}, {}],
    )
    def test_fields_that_cannot_be_edited_or_are_unknown_are_refused(
        self, changes: dict[str, object]
    ) -> None:
        existing = make_product("tente")
        setup = _Setup(existing)

        with pytest.raises(InvalidProductError):
            setup.update.execute(OPERATOR, UpdateProductCommand(existing.id, 1, changes))


class TestArchiveProduct:
    def test_archives_instead_of_deleting_and_is_idempotent(self) -> None:
        existing = make_product("tente")
        setup = _Setup(existing)

        first = setup.archive.execute(OPERATOR, existing.id)
        second = setup.archive.execute(OPERATOR, existing.id)

        assert first.archived_at == NOW
        assert second.version == first.version  # un second archivage ne change plus rien
        assert existing.id in setup.repository.products  # aucune ligne effacée

    def test_an_unknown_product_is_not_found(self) -> None:
        with pytest.raises(ProductNotFoundError):
            _Setup().archive.execute(OPERATOR, "absent")


class TestListAdminProducts:
    def test_hides_archived_products_unless_asked(self) -> None:
        live, gone = make_product("a"), replace(make_product("b"), archived_at=NOW)
        use_case = ListAdminProductsUseCase(InMemoryAdminProducts(live, gone))

        assert [p.id for p in use_case.execute(False, 10, 0).items] == [live.id]
        page = use_case.execute(True, 10, 0)
        assert (page.total, {p.id for p in page.items}) == (2, {live.id, gone.id})


class TestBusinessEvent:
    def test_every_change_emits_one_event_with_a_pseudonymized_actor_and_no_free_text(self) -> None:
        existing = make_product("tente", price_cents=10000, stock=5)
        setup = _Setup(existing)

        setup.create.execute(OPERATOR, _new())
        setup.update.execute(
            OPERATOR, UpdateProductCommand(existing.id, 1, {"price_cents": 12000, "stock": 4})
        )
        setup.archive.execute(OPERATOR, existing.id)

        names = [e.event for e in setup.events.events]
        assert names == ["catalog_admin.change"] * 3
        created, updated, archived = setup.events.events
        assert (created.attributes["action"], created.attributes["old_price_cents"]) == (
            "create",
            None,
        )
        assert updated.attributes == {
            "action": "update",
            "old_price_cents": 10000,
            "new_price_cents": 12000,
            "new_stock": 4,
            "version": 2,
        }
        assert archived.attributes["action"] == "archive"
        assert updated.actor_id == "pseudo-5a1f" and updated.actor_type == "user"
        assert (updated.resource_type, updated.resource_id) == ("product", existing.id)
        dumped = json.dumps([vars(e) for e in setup.events.events], default=str)
        assert OPERATOR_ID not in dumped
        assert "Une tente pour toutes les saisons" not in dumped
