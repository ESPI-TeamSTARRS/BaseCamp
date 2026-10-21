from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UpdateProductCommand:
    """Modification partielle : seuls les champs présents dans `changes` sont touchés."""

    product_id: str
    expected_version: int
    changes: Mapping[str, Any]
