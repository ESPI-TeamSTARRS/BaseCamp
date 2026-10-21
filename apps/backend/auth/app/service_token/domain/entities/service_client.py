from dataclasses import dataclass, field

from app.service_token.domain.enums.service_scope import ServiceScope


@dataclass(frozen=True)
class ServiceClient:
    """Service appelant enregistré : scopes autorisés et empreintes de ses deux secrets valides."""

    client_id: str
    scopes: frozenset[ServiceScope]
    current_secret_hash: str = field(repr=False)
    previous_secret_hash: str | None = field(default=None, repr=False)
