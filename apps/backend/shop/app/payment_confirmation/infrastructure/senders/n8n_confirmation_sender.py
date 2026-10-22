import httpx

from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.errors.confirmation_delivery_error import (
    ConfirmationDeliveryError,
)
from app.payment_confirmation.domain.interfaces.confirmation_sender import ConfirmationSender
from app.payment_confirmation.infrastructure.senders.confirmation_mail_text import (
    ConfirmationMailText,
)
from app.payment_confirmation.infrastructure.senders.mail_html import MailHtml

SECRET_HEADER = "X-Mail-Secret"  # noqa: S105 - nom d'en-tête, pas un secret
_SUCCESS = range(200, 300)


class N8nConfirmationSender(ConfirmationSender):
    """Envoie l'email par le webhook n8n : `POST {to, subject, body}` (HTML) avec l'en-tête secret.

    Redirections non suivies (le secret ne part jamais ailleurs). Tout échec devient une
    `ConfirmationDeliveryError` portant un motif sans donnée sensible.
    """

    def __init__(self, client: httpx.Client, url: str, secret: str, timeout_seconds: float) -> None:
        self._client = client
        self._url = url
        self._secret = secret
        self._timeout = timeout_seconds

    def send(self, mail: ConfirmationMail) -> None:
        if not self._url or not self._secret:
            raise ConfirmationDeliveryError("not_configured")
        payload = {
            "to": mail.to,
            "subject": ConfirmationMailText.subject(mail),
            "body": MailHtml.from_text(ConfirmationMailText.body(mail)),
        }
        try:
            response = self._client.post(
                self._url,
                json=payload,
                headers={SECRET_HEADER: self._secret},
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise ConfirmationDeliveryError("timeout") from None
        except httpx.HTTPError:
            raise ConfirmationDeliveryError("connection_error") from None
        if response.status_code not in _SUCCESS:
            raise ConfirmationDeliveryError(f"http_{response.status_code}")
        if not self._acknowledged(response):
            raise ConfirmationDeliveryError("invalid_response")

    @staticmethod
    def _acknowledged(response: httpx.Response) -> bool:
        try:
            document = response.json()
        except ValueError:
            return False
        return isinstance(document, dict) and document.get("ok") is True
