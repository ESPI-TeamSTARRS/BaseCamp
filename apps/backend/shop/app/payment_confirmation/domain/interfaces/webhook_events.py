from abc import ABC, abstractmethod

from app.payment_confirmation.domain.enums.webhook_outcome import WebhookOutcome


class WebhookEvents(ABC):
    """Mémoire durable des événements reçus : un identifiant n'a d'effet qu'une seule fois."""

    @abstractmethod
    def exists(self, event_id: str) -> bool: ...

    @abstractmethod
    def reason_of(self, event_id: str) -> str | None:
        """Motif enregistré de l'événement (« order_expired »…), None s'il n'en a pas ou est inconnu."""

    @abstractmethod
    def is_order_confirmed(self, order_id: str) -> bool:
        """Vrai si un événement a déjà confirmé le paiement de cette commande."""

    @abstractmethod
    def record(
        self,
        event_id: str,
        event_type: str,
        outcome: WebhookOutcome,
        reason: str | None,
        confirmed_order_id: str | None,
    ) -> None:
        """Enregistre l'événement (écrit au commit); `confirmed_order_id` lie la commande payée."""
