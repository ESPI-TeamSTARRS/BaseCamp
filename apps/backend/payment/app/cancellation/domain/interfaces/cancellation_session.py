from abc import ABC, abstractmethod
from uuid import UUID

from app.intent.domain.entities.payment_intent import PaymentIntent


class CancellationSession(ABC):
    """Une transaction de base de données : l'intention lue est verrouillée jusqu'à la validation."""

    @abstractmethod
    def lock_intent(self, intent_id: UUID) -> PaymentIntent | None:
        """Lit l'intention en posant un verrou de ligne jusqu'à la fin de la transaction."""

    @abstractmethod
    def save(self, intent: PaymentIntent) -> None:
        """Écrit le nouvel état de l'intention verrouillée."""
