from dataclasses import dataclass

from app.caller_identity.domain.enums.token_kind import TokenKind


@dataclass(frozen=True)
class Caller:
    """Appelant identifie par un jeton signe par `auth` : qui (`subject`), de quel type, avec quoi.

    - jeton de SERVICE : `subject` est le client (`shop`), `scopes` ses permissions;
    - jeton CLIENT : `subject` est le compte, `roles` ses roles (un operateur porte `operator`).
    Le jeton lui-meme n'est jamais conserve.
    """

    subject: str
    kind: TokenKind
    scopes: frozenset[str] = frozenset()
    roles: frozenset[str] = frozenset()

    @property
    def actor_type(self) -> str:
        """Type d'acteur des lignes de journal : un service, ou un compte humain (`user`, le schema de journal), ici un operateur."""
        return "service" if self.kind is TokenKind.SERVICE else "user"
