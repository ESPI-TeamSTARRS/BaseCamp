from dataclasses import dataclass


@dataclass(frozen=True)
class DiscrepancyView:
    """Un écart tel que la présentation l'affiche : identifiants et montants seulement."""

    kind: str
    resource_id: str
    expected_cents: int
    observed_cents: int
