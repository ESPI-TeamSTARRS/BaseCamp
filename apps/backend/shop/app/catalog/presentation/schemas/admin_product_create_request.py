from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.catalog.presentation.schemas.admin_specs import AdminSpecs

Cents = Annotated[StrictInt, Field(ge=0, le=10_000_000)]


class AdminProductCreateRequest(BaseModel):
    """Création d'un produit : champs en trop refusés, entiers stricts (jamais de flottant ni de texte)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=200)]
    slug: (
        Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
        | None
    ) = None
    category: Annotated[str, Field(min_length=1, max_length=32)]
    price_cents: Cents
    compare_at_price_cents: Cents | None = None
    short_description: Annotated[str, Field(min_length=1, max_length=300)]
    description: Annotated[str, Field(min_length=1, max_length=5000)]
    specs: AdminSpecs = Field(default_factory=AdminSpecs)
    stock: Annotated[StrictInt, Field(ge=0, le=1_000_000)]
