import smtplib
from email.message import EmailMessage

from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.interfaces.registration_mailer import RegistrationMailer
from app.registration.domain.value_objects.email_address import EmailAddress

VERIFICATION_SUBJECT = "Confirmez votre adresse email - Basecamp Outdoor"
ACCOUNT_EXISTS_SUBJECT = "Un compte existe déjà avec cette adresse - Basecamp Outdoor"

VERIFICATION_BODY = """Bonjour,

Merci de votre inscription chez Basecamp Outdoor. Confirmez votre adresse email en ouvrant ce lien (valable 24 heures, à usage unique) :

{link}

Si vous n'êtes pas à l'origine de cette demande, ignorez simplement ce message : aucun compte ne sera activé.
"""

ACCOUNT_EXISTS_BODY = """Bonjour,

Une inscription vient d'être demandée avec cette adresse email, mais un compte Basecamp Outdoor existe déjà.

Vous pouvez vous connecter avec vos identifiants habituels. Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : votre compte n'a pas été modifié.
"""


class SmtpRegistrationMailer(RegistrationMailer):
    """Envoi SMTP (Mailpit en local). Aucun detail du transport ne remonte : ni adresse, ni jeton."""

    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        public_base_url: str,
        username: str,
        password: str,
        starttls: bool,
        timeout_seconds: float,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._public_base_url = public_base_url.rstrip("/")
        self._username = username
        self._password = password
        self._starttls = starttls
        self._timeout_seconds = timeout_seconds

    def send_verification(self, to: EmailAddress, token: str) -> None:
        link = f"{self._public_base_url}/compte/verification#token={token}"
        self._send(to, VERIFICATION_SUBJECT, VERIFICATION_BODY.format(link=link))

    def send_account_exists(self, to: EmailAddress) -> None:
        self._send(to, ACCOUNT_EXISTS_SUBJECT, ACCOUNT_EXISTS_BODY)

    def _send(self, to: EmailAddress, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to.value
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout_seconds) as smtp:
                if self._starttls:
                    smtp.starttls()
                if self._username:
                    smtp.login(self._username, self._password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            raise MailDeliveryError from None
