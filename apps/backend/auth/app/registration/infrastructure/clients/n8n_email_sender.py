import httpx

from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.interfaces.email_sender import EmailSender
from app.registration.domain.value_objects.email_address import EmailAddress
from app.registration.infrastructure.clients.mail_html import MailHtml

SECRET_HEADER = "X-Mail-Secret"  # noqa: S105 - nom d'en-tete, pas un secret
_SUCCESS = range(200, 300)


class N8nEmailSender(EmailSender):
    """Envoie l'email par le webhook n8n : `POST {to, subject, body}` (HTML) avec l'en-tete secret.

    Les redirections ne sont pas suivies (le secret ne part jamais ailleurs). Tout echec devient une
    `MailDeliveryError` dont le motif (`not_configured`, `timeout`, `connection_error`, `http_403`,
    `invalid_response`) ne contient ni adresse, ni lien, ni secret : n8n voit les liens a usage unique
    en clair (accepte), jamais nos journaux.
    """

    def __init__(self, client: httpx.Client, url: str, secret: str, timeout_seconds: float) -> None:
        self._client = client
        self._url = url
        self._secret = secret
        self._timeout = timeout_seconds

    def send(self, to: EmailAddress, subject: str, body: str) -> None:
        if not self._url or not self._secret:
            raise MailDeliveryError("not_configured")
        payload = {"to": to.value, "subject": subject, "body": MailHtml.from_text(body)}
        try:
            response = self._client.post(
                self._url,
                json=payload,
                headers={SECRET_HEADER: self._secret},
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise MailDeliveryError("timeout") from None
        except httpx.HTTPError:
            raise MailDeliveryError("connection_error") from None
        if response.status_code not in _SUCCESS:
            raise MailDeliveryError(f"http_{response.status_code}")
        if not self._acknowledged(response):
            raise MailDeliveryError("invalid_response")

    @staticmethod
    def _acknowledged(response: httpx.Response) -> bool:
        try:
            document = response.json()
        except ValueError:
            return False
        return isinstance(document, dict) and document.get("ok") is True
