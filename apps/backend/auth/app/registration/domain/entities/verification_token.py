from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

VERIFICATION_TOKEN_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class VerificationToken:
    """Jeton de verification d'email : seul son hachage est conserve, a usage unique."""

    user_id: UUID
    token_hash: str
    expires_at: datetime
    used_at: datetime | None

    @classmethod
    def issue(cls, user_id: UUID, token_hash: str, now: datetime) -> "VerificationToken":
        return cls(user_id, token_hash, now + VERIFICATION_TOKEN_TTL, None)

    def is_usable(self, now: datetime) -> bool:
        return self.used_at is None and now < self.expires_at

    def mark_used(self, now: datetime) -> "VerificationToken":
        return replace(self, used_at=now)
