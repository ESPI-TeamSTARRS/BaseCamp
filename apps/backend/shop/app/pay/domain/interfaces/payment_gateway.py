from abc import ABC, abstractmethod

from app.pay.domain.entities.payment_intent_ref import PaymentIntentRef


class PaymentGateway(ABC):
    """Port vers le service de paiement (adaptateur interne par défaut, fournisseur branchable)."""

    @abstractmethod
    def create_intent(
        self, order_reference: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> PaymentIntentRef:
        """Crée (ou rejoue, à clé identique) l'intention de paiement d'une commande.

        Lève PaymentUnavailableError si le service est injoignable ou saturé, et
        PaymentRejectedError s'il refuse la demande.
        """
