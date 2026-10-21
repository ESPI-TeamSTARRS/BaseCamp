import httpx

from app.core.logging.correlation import outbound_headers
from app.pay.domain.entities.payment_intent_ref import PaymentIntentRef
from app.pay.domain.exceptions.payment_rejected_error import PaymentRejectedError
from app.pay.domain.exceptions.payment_unavailable_error import PaymentUnavailableError
from app.pay.domain.interfaces.payment_gateway import PaymentGateway

HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
SUCCESS_STATUSES = (200, 201)


class HttpPaymentGateway(PaymentGateway):
    """Adaptateur HTTP interne vers `payment` : délais courts, aucune fuite dans les erreurs.

    Le client `httpx` porte les délais (connexion, lecture, écriture, pool) : un `payment`
    arrêté ou saturé fait échouer l'appel vite, jamais bloquer la boutique.
    """

    def __init__(self, client: httpx.Client, service_token: str) -> None:
        self._client = client
        self._service_token = service_token

    def create_intent(
        self, order_reference: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> PaymentIntentRef:
        try:
            response = self._client.post(
                "/payments/intents",
                json={
                    "order_reference": order_reference,
                    "amount": amount_cents,
                    "currency": currency,
                },
                headers={
                    **outbound_headers(),
                    "Authorization": f"Bearer {self._service_token}",
                    "Idempotency-Key": idempotency_key,
                },
            )
        except httpx.HTTPError:
            raise PaymentUnavailableError from None
        if response.status_code in SUCCESS_STATUSES:
            return self._to_intent(response)
        if response.status_code in (HTTP_CONFLICT, HTTP_UNPROCESSABLE):
            raise PaymentRejectedError(conflict=response.status_code == HTTP_CONFLICT)
        raise PaymentUnavailableError  # 401 (config), 429 (saturé), 5xx

    @staticmethod
    def _to_intent(response: httpx.Response) -> PaymentIntentRef:
        try:
            body = response.json()
            return PaymentIntentRef(
                id=str(body["id"]),
                status=str(body["status"]),
                amount_cents=int(body["amount"]),
                currency=str(body["currency"]),
            )
        except (ValueError, KeyError, TypeError):
            raise PaymentUnavailableError from None
