from app.password_reset.domain.interfaces.password_reset_mailer import PasswordResetMailer
from app.registration.domain.interfaces.email_sender import EmailSender
from app.registration.domain.value_objects.email_address import EmailAddress

RESET_SUBJECT = "Réinitialisez votre mot de passe - Basecamp Outdoor"
CHANGED_SUBJECT = "Votre mot de passe a été modifié - Basecamp Outdoor"

RESET_BODY = """Bonjour,

Une réinitialisation du mot de passe de votre compte Basecamp Outdoor a été demandée. Choisissez un nouveau mot de passe en ouvrant ce lien (valable 30 minutes, à usage unique) :

{link}

Si vous n'êtes pas à l'origine de cette demande, ignorez simplement ce message : votre mot de passe actuel reste inchangé.
"""

CHANGED_BODY = """Bonjour,

Le mot de passe de votre compte Basecamp Outdoor vient d'être modifié et toutes vos sessions ont été fermées.

Si vous êtes à l'origine de ce changement, il n'y a rien à faire. Sinon, demandez immédiatement une nouvelle réinitialisation depuis la page « Mot de passe oublié » et contactez-nous.
"""


class EmailPasswordResetMailer(PasswordResetMailer):
    """Le lien ne porte que le jeton, dans le fragment : aucune donnee personnelle, absent des journaux."""

    def __init__(self, transport: EmailSender, public_base_url: str) -> None:
        self._transport = transport
        self._public_base_url = public_base_url.rstrip("/")

    def send_reset_link(self, to: EmailAddress, token: str) -> None:
        link = f"{self._public_base_url}/compte/reinitialiser#token={token}"
        self._transport.send(to, RESET_SUBJECT, RESET_BODY.format(link=link))

    def send_password_changed(self, to: EmailAddress) -> None:
        self._transport.send(to, CHANGED_SUBJECT, CHANGED_BODY)
