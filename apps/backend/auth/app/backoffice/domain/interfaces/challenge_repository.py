from abc import ABC, abstractmethod
from datetime import datetime

from app.backoffice.domain.entities.login_challenge import LoginChallenge


class ChallengeRepository(ABC):
    @abstractmethod
    def add(self, challenge: LoginChallenge) -> None: ...

    @abstractmethod
    def take(self, digest: str, now: datetime) -> LoginChallenge | None:
        """Retire le defi (usage unique) et le rend; `None` s'il est inconnu, expire ou deja pris.

        Un defi expire est supprime au passage. Deux requetes simultanees sur le meme defi se
        serialisent : une seule le recoit.
        """

    @abstractmethod
    def purge_expired(self, now: datetime) -> int:
        """Supprime les defis expires (borne la taille de la table)."""
