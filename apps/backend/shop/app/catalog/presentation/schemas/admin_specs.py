from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt

Measure = Annotated[StrictInt, Field(ge=0, le=1_000_000)]


class AdminSpecs(BaseModel):
    """Caractéristiques techniques (toutes optionnelles, entiers positifs ou nuls)."""

    model_config = ConfigDict(extra="forbid")

    weight_grams: Measure | None = None
    waterproofing_mm: Measure | None = None
    comfort_temp_c: Annotated[StrictInt, Field(ge=-100, le=100)] | None = None
    seasons: Annotated[StrictInt, Field(ge=0, le=4)] | None = None
    capacity_liters: Measure | None = None
    material: Annotated[str, Field(min_length=1, max_length=100)] | None = None
