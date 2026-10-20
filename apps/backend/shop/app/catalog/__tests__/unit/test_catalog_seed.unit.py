"""Le jeu de donnees initial de la migration respecte les invariants du catalogue."""

import importlib.util
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from app.catalog.domain.enums.product_category import ProductCategory

MIGRATION = Path(__file__).resolve().parents[4] / "alembic" / "versions" / "0002_create_products.py"


@pytest.fixture
def seed() -> list[dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("migration_0002", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    products: list[dict[str, Any]] = module.SEED_PRODUCTS
    return products


class TestCatalogSeed:
    def test_contains_fifteen_products_spread_over_five_categories(
        self, seed: list[dict[str, Any]]
    ) -> None:
        counts = Counter(p["category"] for p in seed)

        assert len(seed) == 15
        assert set(counts) == {c.value for c in ProductCategory}
        assert set(counts.values()) == {3}

    def test_slugs_and_ids_are_unique(self, seed: list[dict[str, Any]]) -> None:
        assert len({p["slug"] for p in seed}) == 15
        assert len({p["id"] for p in seed}) == 15

    def test_prices_are_positive_integer_cents(self, seed: list[dict[str, Any]]) -> None:
        assert all(isinstance(p["price_cents"], int) and p["price_cents"] > 0 for p in seed)

    def test_has_at_least_one_sold_out_and_one_low_stock_product(
        self, seed: list[dict[str, Any]]
    ) -> None:
        stocks = [p["stock"] for p in seed]

        assert 0 in stocks
        assert any(0 < s <= 5 for s in stocks)
