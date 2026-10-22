from app.login.domain.exceptions.domain_exception import DomainException


class InvitationRefusedError(DomainException):
    """Une seule erreur pour jeton inconnu, expire, revoque ou deja utilise, adresse bloquee ou compte
    deja cree : rien ne dit laquelle (la route est publique)."""

    def __init__(self) -> None:
        super().__init__("invitation_refused", "Invitation invalide ou expirée.")


class InvitationPasswordError(DomainException):
    """Mot de passe refuse par la politique de l'inscription (12 caracteres minimum...) : 422."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message)


class InvitationPhotoError(DomainException):
    """Photos refusees (nombre, format, taille, aucun visage) : 422, l'invitation n'est pas consommee
    et le compte n'est pas cree."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message)
