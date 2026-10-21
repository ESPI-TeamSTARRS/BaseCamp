from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

PASSWORD_RESET_TOKEN_TTL = timedelta(minutes=30)


@dataclass(frozen=True)
class PasswordResetToken:
    """Jeton de reinitialisation : seul son hachage est conserve, a usage unique, 30 minutes."""

    user_id: UUID
    token_hash: str
    expires_at: datetime
    used_at: datetime | None

    @classmethod
    def issue(cls, user_id: UUID, token_hash: str, now: datetime) -> "PasswordResetToken":
        return cls(user_id, token_hash, now + PASSWORD_RESET_TOKEN_TTL, None)

    def is_usable(self, now: datetime) -> bool:
        return self.used_at is None and now < self.expires_at

    def mark_used(self, now: datetime) -> "PasswordResetToken":
        return replace(self, used_at=now)
