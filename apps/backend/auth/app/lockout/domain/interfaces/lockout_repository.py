from abc import ABC, abstractmethod
from datetime import datetime

from app.lockout.domain.entities.lockout_state import LockoutState


class LockoutRepository(ABC):
    @abstractmethod
    def find(self, scope: str, subject: str) -> LockoutState | None:
        """Lecture simple, sans verrou de ligne (controle avant une tentative)."""

    @abstractmethod
    def lock_for_update(self, scope: str, subject: str, now: datetime) -> LockoutState:
        """Etat du sujet, ligne verrouillee jusqu'a la fin de la transaction (cree s'il manque).

        Deux echecs simultanes du meme sujet se serialisent : aucun n'est perdu, donc le compteur
        est exact meme avec plusieurs instances du service.
        """

    @abstractmethod
    def save(self, state: LockoutState) -> None: ...

    @abstractmethod
    def delete(self, scope: str, subject: str) -> None: ...

    @abstractmethod
    def purge_idle_before(self, cutoff: datetime) -> int:
        """Supprime les sujets inactifs et deverrouilles depuis `cutoff` (borne la taille de la table)."""
