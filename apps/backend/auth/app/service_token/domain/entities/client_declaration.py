import re
from dataclasses import dataclass, field

from app.service_token.domain.enums.service_scope import ServiceScope
from app.service_token.domain.exceptions.invalid_declaration_error import InvalidDeclarationError

CLIENT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MIN_SECRET_LENGTH = 32


@dataclass(frozen=True)
class ClientDeclaration:
    """Client à amorcer : identifiant, scopes et secrets en clair (courant, précédent optionnel)."""

    client_id: str
    scopes: frozenset[ServiceScope]
    current_secret: str = field(repr=False)
    previous_secret: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not CLIENT_ID_PATTERN.fullmatch(self.client_id):
            raise InvalidDeclarationError("invalid client identifier")
        for secret in (self.current_secret, self.previous_secret):
            if secret is not None and len(secret) < MIN_SECRET_LENGTH:
                raise InvalidDeclarationError(
                    f"secret of client {self.client_id} shorter than {MIN_SECRET_LENGTH} characters"
                )
