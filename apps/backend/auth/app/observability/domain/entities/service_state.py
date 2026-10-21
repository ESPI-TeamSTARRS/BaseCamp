from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceState:
    """Etat metier lu en base a la demande (jamais conserve en memoire entre deux lectures)."""

    active_lockouts_by_step: Mapping[str, int]
