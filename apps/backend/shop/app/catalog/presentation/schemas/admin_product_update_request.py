from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.catalog.presentation.schemas.admin_specs import AdminSpecs

Cents = Annotated[StrictInt, Field(ge=0, le=10_000_000)]


class AdminProductUpdateRequest(BaseModel):
    """Modification partielle : `version` (celle lue) est obligatoire, le reste est optionnel."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: Annotated[StrictInt, Field(ge=1)]
    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    category: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    price_cents: Cents | None = None
    compare_at_price_cents: Cents | None = None
    short_description: Annotated[str, Field(min_length=1, max_length=300)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=5000)] | None = None
    specs: AdminSpecs | None = None
    stock: Annotated[StrictInt, Field(ge=0, le=1_000_000)] | None = None
