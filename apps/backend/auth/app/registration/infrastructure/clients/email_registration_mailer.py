from app.registration.domain.interfaces.email_sender import EmailSender
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


class EmailRegistrationMailer(RegistrationMailer):
    """Emails d'inscription, quel que soit le transport. Aucun detail du transport ne remonte :
    ni adresse, ni jeton."""

    def __init__(self, transport: EmailSender, public_base_url: str) -> None:
        self._transport = transport
        self._public_base_url = public_base_url.rstrip("/")

    def send_verification(self, to: EmailAddress, token: str) -> None:
        link = f"{self._public_base_url}/compte/verification#token={token}"
        self._transport.send(to, VERIFICATION_SUBJECT, VERIFICATION_BODY.format(link=link))

    def send_account_exists(self, to: EmailAddress) -> None:
        self._transport.send(to, ACCOUNT_EXISTS_SUBJECT, ACCOUNT_EXISTS_BODY)
