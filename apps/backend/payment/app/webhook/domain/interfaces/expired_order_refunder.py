from abc import ABC, abstractmethod

from app.webhook.domain.entities.outbox_event import OutboxEvent


class ExpiredOrderRefunder(ABC):
    """Rembourse en totalité un paiement que la boutique refuse (commande expirée).

    Idempotent : le même événement ne rembourse jamais deux fois. Lève une erreur si le
    remboursement n'a pas pu être fait : l'événement n'est alors pas clos et sera retenté.
    """

    @abstractmethod
    def refund_in_full(self, event: OutboxEvent) -> None: ...
