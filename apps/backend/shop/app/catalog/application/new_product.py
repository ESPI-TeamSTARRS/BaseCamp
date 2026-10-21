from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NewProduct:
    """Ce que l'administrateur renseigne à la création (valeurs déjà typées par la route)."""

    name: str
    slug: str | None
    category: str
    price_cents: int
    compare_at_price_cents: int | None
    short_description: str
    description: str
    specs: dict[str, Any]
    stock: int
