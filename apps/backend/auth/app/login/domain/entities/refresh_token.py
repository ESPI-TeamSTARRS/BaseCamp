from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4


@dataclass(frozen=True)
class RefreshToken:
    """Jeton de rafraichissement : seul son hachage est conserve (usage livre en A4)."""

    id: UUID
    user_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime

    @classmethod
    def issue(
        cls, user_id: UUID, token_hash: str, now: datetime, ttl_seconds: int
    ) -> "RefreshToken":
        return cls(uuid4(), user_id, token_hash, now, now + timedelta(seconds=ttl_seconds))
