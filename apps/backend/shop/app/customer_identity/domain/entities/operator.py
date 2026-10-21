from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Operator:
    """Opérateur du back-office tel que l'affirme son jeton signé : compte, rôles et méthodes d'authentification (`amr`)."""

    id: UUID
    roles: tuple[str, ...]
    authentication_methods: tuple[str, ...]
