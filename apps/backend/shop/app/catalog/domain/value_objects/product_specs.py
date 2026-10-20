from dataclasses import dataclass


@dataclass(frozen=True)
class ProductSpecs:
    """Caracteristiques techniques affichees en badges (toutes optionnelles)."""

    weight_grams: int | None = None
    waterproofing_mm: int | None = None
    comfort_temp_c: int | None = None
    seasons: int | None = None
    capacity_liters: int | None = None
    material: str | None = None
