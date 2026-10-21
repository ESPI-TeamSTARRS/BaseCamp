import http.client
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from uuid import UUID

from app.webhook.domain.interfaces.webhook_sender import WebhookSender
from app.webhook.domain.value_objects.delivery_result import DeliveryResult
from app.webhook.infrastructure.senders.no_redirect_handler import NoRedirectHandler

_SUCCESS = range(200, 300)
_CONFLICT = 409
_MAX_REJECTION_BYTES = 1024
_REJECTION_REASONS = frozenset({"order_expired"})  # seul refus définitif : commande expirée


class HttpWebhookSender(WebhookSender):
    """POST JSON signé vers la boutique, avec délai borné, sans proxy ni redirection.

    Seuls les schémas http et https sont acceptés. Les échecs sont des codes (`http_503`,
    `timeout`, `connection_error`) : ni l'URL, ni le message d'exception, ni la signature n'en sortent.
    """

    def __init__(self, url: str, timeout_seconds: float) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("the webhook URL must be an http(s) URL")
        self._url = url
        self._timeout = timeout_seconds
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirectHandler()
        )

    def __repr__(self) -> str:
        return f"HttpWebhookSender(timeout_seconds={self._timeout})"

    def send(self, event_id: UUID, body: str, signature: str) -> DeliveryResult:
        request = urllib.request.Request(  # noqa: S310 - schéma http(s) vérifié à la construction
            self._url,
            data=body.encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Payment-Signature": signature,
                "X-Payment-Event-Id": str(event_id),
                "User-Agent": "basecamp-payment-webhook/1",
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                status = int(response.status)
        except urllib.error.HTTPError as error:
            reason = self._rejection_reason(error) if error.code == _CONFLICT else None
            error.close()
            if reason is not None:
                return DeliveryResult.rejection(reason, error.code)
            return self._answer(error.code)
        except TimeoutError:
            return DeliveryResult.failed("timeout")
        except urllib.error.URLError as error:
            return DeliveryResult.failed(
                "timeout" if isinstance(error.reason, TimeoutError) else "connection_error"
            )
        except (OSError, http.client.HTTPException):
            return DeliveryResult.failed("connection_error")
        return self._answer(status)

    @staticmethod
    def _rejection_reason(error: urllib.error.HTTPError) -> str | None:
        """Motif d'un 409 de la boutique (corps `{"status": "rejected", "reason": "order_expired"}`)."""
        try:
            document = json.loads(error.read(_MAX_REJECTION_BYTES))
        except (ValueError, OSError, http.client.HTTPException):
            return None
        if not isinstance(document, dict) or document.get("status") != "rejected":
            return None
        reason = document.get("reason")
        return reason if isinstance(reason, str) and reason in _REJECTION_REASONS else None

    @staticmethod
    def _answer(status: int) -> DeliveryResult:
        if status in _SUCCESS:
            return DeliveryResult.ok(status)
        return DeliveryResult.failed(f"http_{status}", status)
