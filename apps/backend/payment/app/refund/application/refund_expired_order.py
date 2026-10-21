import json

from app.refund.application.commands.refund_payment_command import RefundPaymentCommand
from app.refund.application.refund_payment import RefundPaymentUseCase
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.interfaces.expired_order_refunder import ExpiredOrderRefunder

CALLER = "payment-worker"
KEY_PREFIX = "auto-refund-"


class RefundExpiredOrderUseCase(ExpiredOrderRefunder):
    """Rembourse le capturé d'un paiement refusé par la boutique, par le cas d'usage de remboursement.

    La clé d'idempotence dérive de l'identifiant de l'événement (constant à chaque relance) : un
    rejeu retrouve le remboursement déjà fait, sans écriture ni second événement.
    """

    def __init__(self, refund: RefundPaymentUseCase) -> None:
        self._refund = refund

    def refund_in_full(self, event: OutboxEvent) -> None:
        self._refund.execute(
            RefundPaymentCommand(
                caller=CALLER,
                idempotency_key=f"{KEY_PREFIX}{event.id}",
                intent_id=str(event.intent_id),
                amount=_captured_amount(event.body),
            )
        )


def _captured_amount(body: str) -> int:
    try:
        data = json.loads(body).get("data")
        amount = data.get("amount") if isinstance(data, dict) else None
    except (ValueError, AttributeError):
        amount = None
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ValueError("the event body carries no usable amount")
    return amount
