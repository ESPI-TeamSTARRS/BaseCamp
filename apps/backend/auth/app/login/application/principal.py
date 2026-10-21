from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Principal:
    """Appelant authentifie : identifiant du compte et roles lus dans le jeton signe."""

    id: UUID
    roles: tuple[str, ...]

    def has_any(self, required: frozenset[str]) -> bool:
        return bool(required.intersection(self.roles))
