from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.login.domain.entities.account import Account


@dataclass(frozen=True)
class AccessTokenClaims:
    """Ce qu'un jeton d'acces affirme : qui, quels roles, jusqu'a quand, sous quel identifiant."""

    subject: UUID
    roles: tuple[str, ...]
    email_verified: bool
    issued_at: datetime
    expires_at: datetime
    token_id: str

    @classmethod
    def issue(
        cls, account: Account, now: datetime, ttl_seconds: int, token_id: str
    ) -> "AccessTokenClaims":
        return cls(
            account.id,
            (account.role,),
            account.email_verified,
            now,
            now + timedelta(seconds=ttl_seconds),
            token_id,
        )
