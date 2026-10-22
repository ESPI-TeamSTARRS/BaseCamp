from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.login.domain.entities.account import Account

OPERATOR_ROLE = "operator"
AMR_FACE = "face"
AMR_PASSWORD = "pwd"  # noqa: S105 - methode d'authentification (RFC 8176), pas un secret


@dataclass(frozen=True)
class AccessTokenClaims:
    """Ce qu'un jeton d'acces affirme : qui, quels roles, jusqu'a quand, sous quel identifiant.

    `amr` (methodes d'authentification, RFC 8176) n'est renseigne que par la connexion du back-office
    en trois temps (`face`, `pwd`) : le role `operator` ne sort que de cette connexion.
    """

    subject: UUID
    roles: tuple[str, ...]
    email_verified: bool
    issued_at: datetime
    expires_at: datetime
    token_id: str
    amr: tuple[str, ...] = ()

    @classmethod
    def issue(
        cls, account: Account, now: datetime, ttl_seconds: int, token_id: str
    ) -> "AccessTokenClaims":
        """Connexion classique du site client : jamais le role `operator`, jamais d'`amr`."""
        roles = tuple(role for role in (account.role,) if role != OPERATOR_ROLE)
        return cls(
            account.id,
            roles,
            account.email_verified,
            now,
            now + timedelta(seconds=ttl_seconds),
            token_id,
        )

    @classmethod
    def issue_operator(
        cls, account: Account, now: datetime, ttl_seconds: int, token_id: str
    ) -> "AccessTokenClaims":
        """Fin de la connexion en trois temps : `operator` et `amr=[face, pwd]`."""
        return cls(
            account.id,
            (OPERATOR_ROLE,),
            account.email_verified,
            now,
            now + timedelta(seconds=ttl_seconds),
            token_id,
            (AMR_FACE, AMR_PASSWORD),
        )
