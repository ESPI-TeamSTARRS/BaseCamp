from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4


@dataclass(frozen=True)
class RefreshToken:
    """Jeton de rafraichissement : seul son hachage est conserve.

    Les jetons d'une meme connexion forment une famille (`family_id`) : chaque rafraichissement
    consomme le jeton (`used_at`) et en emet un nouveau dans la meme famille. Un jeton deja consomme
    qui revient est un rejeu : toute la famille est revoquee.
    """

    id: UUID
    user_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    family_id: UUID
    used_at: datetime | None = None

    @classmethod
    def issue(
        cls,
        user_id: UUID,
        token_hash: str,
        now: datetime,
        ttl_seconds: int,
        family_id: UUID | None = None,
    ) -> "RefreshToken":
        token_id = uuid4()
        return cls(
            token_id,
            user_id,
            token_hash,
            now,
            now + timedelta(seconds=ttl_seconds),
            family_id or token_id,
        )

    def successor(self, token_hash: str, now: datetime, ttl_seconds: int) -> "RefreshToken":
        """Jeton qui prend la suite de celui-ci, dans la meme famille et avec une duree neuve."""
        return RefreshToken.issue(self.user_id, token_hash, now, ttl_seconds, self.family_id)

    def expired(self, now: datetime) -> bool:
        return self.expires_at <= now

    def consumed(self, now: datetime) -> "RefreshToken":
        return replace(self, used_at=now)
