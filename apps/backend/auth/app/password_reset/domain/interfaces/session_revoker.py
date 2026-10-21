from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID


class SessionRevoker(ABC):
    """Point d'integration avec les sessions (jetons de rafraichissement).

    L'implementation participe a la transaction de la reinitialisation : si le mot de passe ne
    change pas, aucune session n'est revoquee, et inversement.
    """

    @abstractmethod
    def revoke_all(self, user_id: UUID, now: datetime) -> None:
        """Rend invalides toutes les sessions du compte emises avant `now`."""
