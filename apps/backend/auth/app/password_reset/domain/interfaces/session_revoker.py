from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID


class SessionRevoker(ABC):
    """Point d'integration avec les sessions (jetons de rafraichissement de la connexion).

    L'implementation participe a la transaction de la reinitialisation : si le mot de passe ne
    change pas, aucune session n'est revoquee, et inversement.
    """

    @abstractmethod
    def revoke_all(self, user_id: UUID, now: datetime) -> int:
        """Revoque toute la famille de sessions du compte; renvoie le nombre de sessions revoquees.

        Un jeton d'acces deja emis n'est pas concerne : il expire seul (15 minutes au plus).
        """
