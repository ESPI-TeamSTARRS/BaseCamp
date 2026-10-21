from abc import ABC, abstractmethod

from app.pay.domain.entities.payment_intent_ref import PaymentIntentRef


class PaymentGateway(ABC):
    """Port vers le fournisseur de paiement (service `payment` ou adaptateur simulé).

    Tous les appels lèvent PaymentUnavailableError si le fournisseur est injoignable ou saturé, et
    PaymentRejectedError s'il refuse la demande (règle métier).
    """

    @abstractmethod
    def create_intent(
        self, order_reference: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> PaymentIntentRef:
        """Crée (ou rejoue, à clé identique) l'intention de paiement d'une commande."""

    @abstractmethod
    def get_intent(self, intent_id: str) -> PaymentIntentRef:
        """Lit une intention (statut courant)."""

    @abstractmethod
    def confirm_intent(
        self, intent_id: str, payment_method: str, idempotency_key: str
    ) -> PaymentIntentRef:
        """Confirme l'intention avec une méthode de test (jamais de donnée de carte)."""
