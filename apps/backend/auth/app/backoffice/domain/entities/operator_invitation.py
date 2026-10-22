from dataclasses import dataclass, replace
from datetime import datetime, timedelta

MAX_LIFETIME_SECONDS = 300  # 5 minutes au plus : le lien est une cle d'acces


@dataclass(frozen=True)
class OperatorInvitation:
    """Invitation a usage unique : liee a une adresse, valable 5 minutes au plus.

    `digest` est l'empreinte du jeton (jamais le jeton). Une invitation n'est utilisable que si elle
    n'est ni expiree, ni revoquee, ni deja consommee.
    """

    digest: str
    email: str
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None

    @classmethod
    def issue(
        cls, digest: str, email: str, now: datetime, ttl_seconds: int
    ) -> "OperatorInvitation":
        lifetime = min(ttl_seconds, MAX_LIFETIME_SECONDS)
        return cls(digest, email, now, now + timedelta(seconds=lifetime))

    def usable(self, now: datetime) -> bool:
        return self.consumed_at is None and self.revoked_at is None and now < self.expires_at

    def consumed(self, now: datetime) -> "OperatorInvitation":
        return replace(self, consumed_at=now)
