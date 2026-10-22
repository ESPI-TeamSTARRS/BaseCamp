from abc import ABC, abstractmethod
from datetime import datetime

from app.backoffice.domain.entities.operator_invitation import OperatorInvitation


class InvitationRepository(ABC):
    @abstractmethod
    def add(self, invitation: OperatorInvitation) -> None: ...

    @abstractmethod
    def find(self, digest: str) -> OperatorInvitation | None:
        """Lecture simple, sans verrou (controle avant le calcul d'enrolement)."""

    @abstractmethod
    def claim(self, digest: str, now: datetime) -> OperatorInvitation | None:
        """Ligne verrouillee jusqu'a la fin de la transaction; `None` si l'invitation n'est plus
        utilisable (inconnue, expiree, revoquee, deja consommee). Deux completions simultanees se
        serialisent : une seule recoit l'invitation."""

    @abstractmethod
    def mark_consumed(self, digest: str, now: datetime) -> None: ...

    @abstractmethod
    def revoke_active_for(self, email: str, now: datetime) -> int:
        """Revoque les invitations encore utilisables de cette adresse; renvoie leur nombre."""

    @abstractmethod
    def purge_before(self, cutoff: datetime) -> int:
        """Supprime les invitations expirees avant `cutoff` (borne la taille de la table)."""
