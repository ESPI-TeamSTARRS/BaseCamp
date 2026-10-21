from collections.abc import Mapping
from dataclasses import fields
from typing import Any

from app.catalog.application.invalid_product_error import InvalidProductError
from app.catalog.domain.enums.product_category import ProductCategory
from app.catalog.domain.value_objects.product_specs import ProductSpecs

_SPEC_NUMBERS = {f.name for f in fields(ProductSpecs) if f.name != "material"}
_MAX_MATERIAL = 100
_MAX_PRICE_CENTS = 10_000_000
_MAX_STOCK = 1_000_000


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _bounded(value: object, maximum: int, reason: str) -> int:
    """Entier (jamais un booléen) compris entre 0 et `maximum`."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise InvalidProductError(reason)
    return value


class ProductValidator:
    """Règles métier des données de produit (en plus de la validation de forme de la route)."""

    @staticmethod
    def category(value: object) -> ProductCategory:
        try:
            return ProductCategory(str(value))
        except ValueError:
            raise InvalidProductError("category_invalid") from None

    @staticmethod
    def text(value: object, reason: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise InvalidProductError(reason)
        return value.strip()

    @staticmethod
    def price(value: object, reason: str = "price_invalid") -> int:
        return _bounded(value, _MAX_PRICE_CENTS, reason)

    @staticmethod
    def optional_price(value: object) -> int | None:
        return None if value is None else ProductValidator.price(value, "compare_price_invalid")

    @staticmethod
    def stock(value: object) -> int:
        return _bounded(value, _MAX_STOCK, "stock_invalid")

    @staticmethod
    def specs(value: object) -> ProductSpecs:
        if not isinstance(value, Mapping):
            raise InvalidProductError("specs_invalid")
        checked: dict[str, Any] = {}
        for key, item in value.items():
            if item is None:
                continue
            if (key in _SPEC_NUMBERS and _is_integer(item) and item >= 0) or (
                key == "material" and isinstance(item, str) and 0 < len(item) <= _MAX_MATERIAL
            ):
                checked[key] = item
            else:
                raise InvalidProductError("specs_invalid")
        return ProductSpecs(**checked)
