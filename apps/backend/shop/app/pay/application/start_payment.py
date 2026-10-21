from collections.abc import Sequence

from app.cart.application.invalid_cart_error import InvalidCartError
from app.cart.application.quote_cart import QuoteCartUseCase
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.pay.domain.entities.payment_intent_ref import PaymentIntentRef
from app.pay.domain.exceptions.payment_rejected_error import PaymentRejectedError
from app.pay.domain.exceptions.payment_unavailable_error import PaymentUnavailableError
from app.pay.domain.interfaces.payment_gateway import PaymentGateway

CURRENCY = "EUR"
STARTED_EVENT = "pay.payment_started"
REJECTED_EVENT = "pay.payment_rejected"
UNAVAILABLE_EVENT = "pay.payment_unavailable"


class StartPaymentUseCase:
    """Démarre le paiement d'un panier : le montant est celui du devis serveur, jamais du client."""

    def __init__(
        self, quote_cart: QuoteCartUseCase, gateway: PaymentGateway, events: BusinessEventLogger
    ) -> None:
        self._quote_cart = quote_cart
        self._gateway = gateway
        self._events = events

    def execute(
        self, order_reference: str, items: Sequence[tuple[str, int]], idempotency_key: str
    ) -> PaymentIntentRef:
        quote = self._quote_cart.execute(items)
        if quote.has_issues:
            self._events.log(BusinessEvent.denied(REJECTED_EVENT, "insufficient_stock"))
            raise InvalidCartError(
                "Stock insuffisant pour une ou plusieurs lignes.", "insufficient_stock"
            )
        try:
            intent = self._gateway.create_intent(
                order_reference, quote.total_cents, CURRENCY, idempotency_key
            )
        except PaymentUnavailableError:
            self._events.log(BusinessEvent.error(UNAVAILABLE_EVENT, "payment_unavailable"))
            raise
        except PaymentRejectedError as error:
            reason = "payment_conflict" if error.conflict else "payment_refused"
            self._events.log(BusinessEvent.denied(REJECTED_EVENT, reason))
            raise
        self._events.log(
            BusinessEvent.success(
                STARTED_EVENT,
                resource_type="payment_intent",
                resource_id=intent.id,
                attributes={"amount_cents": intent.amount_cents, "currency": intent.currency},
            )
        )
        return intent
