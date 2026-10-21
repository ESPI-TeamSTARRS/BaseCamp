from dataclasses import dataclass


@dataclass(frozen=True)
class RequestKey:
    """Cle d'une serie de requetes : route en gabarit, methode et statut (jamais de valeur libre)."""

    route: str
    method: str
    status: int
